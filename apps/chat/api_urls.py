from django.urls import path

from . import api

urlpatterns = [
    path("chat/ask/", api.Ask.as_view(), name="api-chat-ask"),
    path("chat/conversations/", api.Conversations.as_view(), name="api-conversations"),
    path("chat/conversations/<int:pk>/", api.ConversationDetail.as_view(), name="api-conversation"),
    path("chat/messages/<int:pk>/feedback/", api.FeedbackView.as_view(), name="api-feedback"),
]
