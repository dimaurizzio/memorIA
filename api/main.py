"""FastAPI app — punto de entrada de la API REST."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes.documents import router as documents_router
from api.routes.agents import router as agents_router
from api.routes.admin import router as admin_router
from api.routes.chat import router as chat_router

app = FastAPI(title="memorIA API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents_router)
app.include_router(agents_router)
app.include_router(admin_router)
app.include_router(chat_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/spec/{object_type}")
def get_spec_for_type(object_type: str):
    """Spec completo (secciones + campos) para un tipo. Usado por el viewer/editor del frontend."""
    from config.doc_spec import spec_to_dict, supported_types
    from fastapi import HTTPException
    if object_type not in supported_types():
        raise HTTPException(status_code=404, detail=f"Tipo '{object_type}' no soportado.")
    return spec_to_dict(object_type)


@app.get("/spec/types")
def get_object_types():
    """
    Retorna los tipos de objeto soportados con sus metadatos de presentación.
    Deriva de config.doc_spec — no hay valores hardcodeados.
    """
    from config.object_types import OBJECT_TYPES
    return [
        {
            "value": key,
            "label": cfg["label"],
            "display_name": cfg["display_name"],
            "icon": cfg["icon"],
        }
        for key, cfg in OBJECT_TYPES.items()
    ]


@app.get("/toolbox/objects")
async def list_toolbox_objects(object_type: str | None = None):
    """
    Lista objetos disponibles en las fuentes de datos.
    Cada objeto incluye: name, type, connection, database_name.
    Filtro opcional: object_type=table|view
    """
    from tools.mcp_client import list_objects
    return await list_objects(object_type)
