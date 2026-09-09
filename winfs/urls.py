from django.urls import path

from . import views

urlpatterns = [
    path("", views.volume_list, name="winfs-volumes"),
    path("volume/<int:pk>/", views.volume_root, name="winfs-volume"),
    path("node/<int:pk>/", views.browse, name="winfs-node"),
]
