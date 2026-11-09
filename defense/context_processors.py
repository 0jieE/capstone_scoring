from django.conf import settings


def institution(request):
    return {"INSTITUTION": settings.INSTITUTION}
