from django.urls import path
from pilot import coview, devices, views

urlpatterns = [
    path("",devices.launch,name="device_launch"),
    path("manifest.webmanifest",devices.manifest,name="manifest"),
    path("worker.js",devices.worker,name="device_worker"),
    path("pair/",devices.pair,name="pair"),
    path("prove/",devices.prove,name="prove"),
    path("garden/",views.home,name="home"),
    path("play/<int:pk>/",views.play,name="play"),
    path("suggestions/start/",views.start_suggestion,name="start_suggestion"),
    path("co-view/share/<int:pk>/",coview.broadcast,name="coview_broadcast"),
]
