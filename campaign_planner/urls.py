"""campaign_planner URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.urls import include, path
from campaigns.views import deliverable_file

urlpatterns = [
    path('', include('campaigns.urls')),
    path('admin/', admin.site.urls),
    # Keep existing file links, but check campaign permissions before serving.
    path(settings.MEDIA_URL.lstrip('/') + '<path:file_path>', deliverable_file, name='deliverable_file'),
]
