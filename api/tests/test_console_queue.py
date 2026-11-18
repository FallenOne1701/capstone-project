"""Queue fields the console UI needs (Plan 3 Task 9)."""

from app.models import Action, Draft, Ticket

H = {"X-Console-Key": "test-pass"}


def test_queue_action_includes_error(client, db_session):
    t = Ticket(code="GRW-QUEUE1", channel="text", language="en", question_redacted="q", pii_types=[],
               intent="fee_question", status="in_review")
    db_session.add(t)
    db_session.flush()
    d = Draft(ticket_id=t.id, reply="r", disposition="reply", routing_team="x", routing_priority="P3",
              routing_why="y", review_status="pass")
    db_session.add(d)
    db_session.flush()
    db_session.add(Action(type="reply_publish", target_label="Reply", target_ref=t.code, draft_id=d.id,
                          status="failed", error="boom"))
    db_session.commit()
    item = next(i for i in client.get("/api/console/queue", headers=H).json() if i["code"] == "GRW-QUEUE1")
    assert item["action"]["error"] == "boom"
