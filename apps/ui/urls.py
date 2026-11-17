from django.urls import path

from . import views

app_name = "ui"
urlpatterns = [
    path("", views.home, name="home"),
    path("chat/", views.chat, name="chat"),
    path("documents/", views.documents, name="documents"),
    path("testcases/", views.testcases, name="testcases"),
]
