from django.contrib import admin

# Register your models here.
from .models import QueryLog

admin.site.register(QueryLog)