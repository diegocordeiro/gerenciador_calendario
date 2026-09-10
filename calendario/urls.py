from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("editor/", views.editor, name="editor"),
    path("versoes/", views.versoes, name="versoes"),
    path("calendario/", views.calendario_atual, name="calendario_atual"),
    path("calendario/<str:slug>/", views.calendario_versionado, name="calendario_versionado"),
    path("versoes/<str:slug>/", views.calendario_versionado, name="calendario_versao"),
    path("api/preview/", views.api_preview, name="api_preview"),
    path("api/salvar/", views.api_salvar, name="api_salvar"),
    path("api/excluir/", views.api_excluir, name="api_excluir"),
    path(
        "api/feriados-nacionais/",
        views.api_feriados_nacionais,
        name="api_feriados_nacionais",
    ),
]
