from django.db import models

# Create your models here.

class QueryLog(models.Model):
    case_type = models.CharField(max_length=50)
    case_number = models.CharField(max_length=50)
    case_year = models.CharField(max_length=4)
    query_timestamp = models.DateTimeField(auto_now_add=True)
    raw_response = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20) # e.g., 'SUCCESS' or 'ERROR'
    error_message = models.CharField(max_length=300, null=True, blank=True)

    def __str__(self):
        return f"{self.case_type} {self.case_number}/{self.case_year} - {self.status}"