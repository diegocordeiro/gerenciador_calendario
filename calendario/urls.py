from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("editor/", views.editor, name="editor"),
    path("versoes/", views.versoes, name="versoes"),
    path("versoes/excluir/", views.excluir_versao, name="excluir_versao"),
    path("versoes/clonar/", views.clonar_versao, name="clonar_versao"),
    path("calendario/", views.calendario_atual, name="calendario_atual"),
    path("calendario/<str:slug>/", views.calendario_versionado, name="calendario_versionado"),
    path("versoes/<str:slug>/", views.calendario_versionado, name="calendario_versao"),
    path("api/preview/", views.api_preview, name="api_preview"),
    path("api/salvar/", views.api_salvar, name="api_salvar"),
    path("api/excluir/", views.api_excluir, name="api_excluir"),
    path("api/clonar/", views.api_clonar, name="api_clonar"),
    path("api/eventos/", views.api_eventos, name="api_eventos"),
    path(
        "api/feriados-nacionais/",
        views.api_feriados_nacionais,
        name="api_feriados_nacionais",
    ),
]
