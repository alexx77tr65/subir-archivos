from io import BytesIO
from math import isfinite
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from xhtml2pdf import pisa

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=BASE_DIR.parent)

app = FastAPI(title="xhtml2pdf Demo")

app.mount("/assets", StaticFiles(directory=BASE_DIR / "assets"), name="assets")

PRODUCTS: list[dict] = [
    {
        "id": 1,
        "name": "Laptop Pro 14",
        "category": "Computo",
        "price": 18999.00,
        "stock": 12,
    },
    {
        "id": 2,
        "name": 'Monitor 27" 4K',
        "category": "Pantallas",
        "price": 7499.50,
        "stock": 30,
    },
    {
        "id": 3,
        "name": "Teclado Mecanico",
        "category": "Accesorios",
        "price": 1299.99,
        "stock": 85,
    },
    {
        "id": 4,
        "name": "Mouse Inalambrico",
        "category": "Accesorios",
        "price": 499.00,
        "stock": 120,
    },
    {
        "id": 5,
        "name": "Webcam Full HD",
        "category": "Video",
        "price": 899.00,
        "stock": 45,
    },
]


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": "xhtml2pdf Demo",
            "products_count": len(PRODUCTS),
            "products": PRODUCTS,
            "added": request.query_params.get("added") == "1",
        },
    )


@app.post("/products")
async def add_product(request: Request) -> Response:
    if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
        raise HTTPException(status_code=415, detail="El formulario debe enviarse como datos URL-encoded.")

    try:
        form = parse_qs((await request.body()).decode("utf-8"), strict_parsing=True)
    except (UnicodeDecodeError, ValueError) as error:
        raise HTTPException(status_code=400, detail="No se pudo leer el formulario.") from error

    def get_field(name: str) -> str:
        values = form.get(name)
        if not values or len(values) != 1:
            raise HTTPException(status_code=422, detail=f"El campo {name} es obligatorio.")
        return values[0].strip()

    name = get_field("name")
    category = get_field("category")
    if not name or not category:
        raise HTTPException(status_code=422, detail="El nombre y la categoría son obligatorios.")

    try:
        price = float(get_field("price"))
        stock = int(get_field("stock"))
    except ValueError as error:
        raise HTTPException(status_code=422, detail="El precio o el stock no tienen un formato válido.") from error

    if not isfinite(price) or price < 0 or stock < 0:
        raise HTTPException(status_code=422, detail="El precio y el stock deben ser valores positivos.")

    PRODUCTS.append(
        {
            "id": max(product["id"] for product in PRODUCTS) + 1,
            "name": name,
            "category": category,
            "price": price,
            "stock": stock,
        }
    )
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse(content={"product": PRODUCTS[-1]})
    return RedirectResponse(url="/?added=1", status_code=303)


@app.get("/report", response_class=HTMLResponse)
async def preview_report(request: Request) -> HTMLResponse:
    """Muestra el reporte en HTML antes de descargarlo como PDF."""
    return templates.TemplateResponse(
        request=request,
        name="report.html",
        context={
            "title": "Catalogo de Productos",
            "products": PRODUCTS,
            "preview": True,
        },
    )


@app.get("/report/logo", response_class=HTMLResponse)
async def preview_report_with_logo(request: Request) -> HTMLResponse:
    """Preview del reporte con logo (el logo se sirve por URL en la web)."""
    return templates.TemplateResponse(
        request=request,
        name="templates/report_logo.html",
        context={
            "title": "Catalogo de Productos",
            "products": PRODUCTS,
            "preview": True,
            # En el navegador el src debe ser una URL.
            "logo_src": str(request.url_for("assets", path="logo.png")),
            # Solo para mostrar en el preview la ruta absoluta que usara el PDF.
            "logo_pdf_path": str(BASE_DIR / "assets" / "logo.png"),
        },
    )


@app.get("/report/pdf")
def download_report() -> Response:
    """Genera el PDF a partir de puro HTML (sin imagenes)."""
    html = templates.get_template("report.html").render(
        title="Catalogo de Productos",
        products=PRODUCTS,
        preview=False,
    )
    pdf_buffer = BytesIO()
    result = pisa.CreatePDF(src=html, dest=pdf_buffer)
    return _pdf_response(pdf_buffer, result, "report.pdf")


@app.get("/report/pdf-logo")
def download_report_with_logo() -> Response:
    """Genera el PDF con logo usando una ruta absoluta en la etiqueta img."""
    html = templates.get_template("templates/report_logo.html").render(
        title="Catalogo de Productos",
        products=PRODUCTS,
        preview=False,
        # Para xhtml2pdf el logo se pasa como ruta absoluta de disco.
        logo_src=str(BASE_DIR / "assets" / "logo.png"),
    )
    pdf_buffer = BytesIO()
    result = pisa.CreatePDF(src=html, dest=pdf_buffer)
    return _pdf_response(pdf_buffer, result, "report_con_logo.pdf")


def _pdf_response(pdf_buffer: BytesIO, result, filename: str) -> Response:
    if result.err:
        raise HTTPException(
            status_code=500,
            detail=f"Error al generar el PDF ({result.err} errores)",
        )
    return Response(
        content=pdf_buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )