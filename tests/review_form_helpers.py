"""Supply the revision fields that real rendered review forms now include."""
import re

from app.extensions import db
from app.models import TestCaseDraft


def with_review_revisions(client, app):
    original_post = client.post

    def post(path, *args, **kwargs):
        matched = re.fullmatch(r"/ai-test-design/drafts/(\d+)/(?:edit|accept|reject)", path)
        if matched:
            data = dict(kwargs.get("data") or {})
            with app.app_context():
                draft = db.session.get(TestCaseDraft, int(matched.group(1)))
                if draft is not None:
                    data.setdefault("draft_revision", str(draft.revision))
                    data.setdefault("session_revision", str(draft.session.review_revision))
            kwargs["data"] = data
        return original_post(path, *args, **kwargs)

    client.post = post
    return client
