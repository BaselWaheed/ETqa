from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sysconfig.services import get as setting

from . import services
from .models import Conversation, Feedback, Message


class AskSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=4000)
    conversation_id = serializers.IntegerField(required=False, allow_null=True)
    collection_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    history = serializers.ListField(child=serializers.DictField(), required=False, max_length=8)


class Ask(APIView):
    def post(self, request):
        ser = AskSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            body = services.ask(user=request.user, request=request, **ser.validated_data)
        except services.ChatNotAllowed as exc:
            return Response({"detail": str(exc)}, status=403)
        except Conversation.DoesNotExist:
            return Response({"detail": "Conversation not found."}, status=404)
        body["poll_running_ms"] = setting("chat.poll_running_ms")
        body["poll_idle_ms"] = setting("chat.poll_idle_ms")
        return Response(body, status=200 if "immediate" in body else 202)


def _message_dict(m: Message) -> dict:
    return {"id": m.pk, "role": m.role, "content": m.content, "evidence": m.evidence, "job_id": m.job_id,
            "created_at": m.created_at, "citations": [
                {"marker": c.marker, "document_id": c.document_id, "title": c.title, "version_no": c.version_no,
                 "locator": c.locator, "section_path": c.section_path, "excerpt": c.excerpt} for c in m.citations.all()]}


class Conversations(APIView):
    def get(self, request):
        rows = Conversation.objects.filter(user=request.user, archived=False).values("id", "title", "updated_at")[:100]
        return Response(list(rows))


class ConversationDetail(APIView):
    def get(self, request, pk: int):
        conv = get_object_or_404(Conversation, pk=pk, user=request.user)
        msgs = conv.messages.prefetch_related("citations")
        return Response({"id": conv.pk, "title": conv.title, "messages": [_message_dict(m) for m in msgs]})

    def delete(self, request, pk: int):
        Conversation.objects.filter(pk=pk, user=request.user).update(archived=True)
        return Response(status=204)


class FeedbackView(APIView):
    def post(self, request, pk: int):
        if not request.user.has_perm("access.give_feedback"):
            return Response(status=403)
        message = get_object_or_404(Message, pk=pk, role="assistant", conversation__user=request.user)
        try:
            rating = int(request.data.get("rating"))
            assert rating in (1, -1)
        except (TypeError, ValueError, AssertionError):
            return Response({"detail": "rating must be 1 or -1"}, status=400)
        Feedback.objects.update_or_create(message=message, user=request.user, defaults={
            "rating": rating, "comment": str(request.data.get("comment", ""))[:4000],
            "suggested_answer": str(request.data.get("suggested_answer", ""))[:8000]})
        return Response({"saved": True}, status=201)
