from django.conf import settings


def app_version(request):
    return {
        "app_commit_sha": settings.APP_COMMIT_SHA,
        "app_commit_date": settings.APP_COMMIT_DATE,
    }
