from django.apps import AppConfig


class CampaignsConfig(AppConfig):
    # Keep new implicit primary keys consistent with migration 0004 and the
    # existing database, which use AutoField for this app.
    default_auto_field = 'django.db.models.AutoField'
    name = 'campaigns'
