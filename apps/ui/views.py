from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.access.models import Collection
from apps.access.services import scope_for
from apps.access.scope import can_upload
from apps.sysconfig.services import get as setting


def _collections(request):
    scope = scope_for(request.user)
    return scope, list(Collection.objects.filter(id__in=scope.readable, is_active=True))


@login_required
def home(request):
    _, collections = _collections(request)
    roles = sorted(request.user.groups.values_list("name", flat=True))
    return render(request, "ui/home.html", {"collections": collections, "roles": roles, "page": "home"})


@login_required
def chat(request):
    _, collections = _collections(request)
    config = {"saved": request.user.has_perm("access.save_chat_history"),
              "feedback": request.user.has_perm("access.give_feedback"),
              "collections": [{"id": c.id, "name": c.name} for c in collections],
              "poll_running_ms": setting("chat.poll_running_ms"), "poll_idle_ms": setting("chat.poll_idle_ms")}
    return render(request, "ui/chat.html", {"config": config, "page": "chat"})


@login_required
def documents(request):
    scope, collections = _collections(request)
    config = {"upload_collections": [{"id": c.id, "name": c.name} for c in collections if can_upload(request.user, scope, c.id)],
              "manage": sorted(scope.manageable), "can_delete": request.user.has_perm("access.delete_documents")}
    return render(request, "ui/documents.html", {"config": config, "page": "documents"})


@login_required
def testcases(request):
    _, collections = _collections(request)
    config = {"allowed": request.user.has_perm("access.generate_test_cases"),
              "export": request.user.has_perm("access.export_excel"),
              "collections": [{"id": c.id, "name": c.name} for c in collections]}
    return render(request, "ui/testcases.html", {"config": config, "page": "testcases"})
