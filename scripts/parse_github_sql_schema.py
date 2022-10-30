#!/usr/bin/env python

from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, Text, ForeignKey, Boolean
from enum import IntEnum

SQLBase = declarative_base()


def IdColumn():
    return Column(Integer, primary_key=True, autoincrement=True)


def ForeignId(name: str, nullable: bool = False):
    return Column(Integer, ForeignKey(name), nullable=nullable)


def IntColumn(nullable: bool = False):
    return Column(Integer, nullable=nullable)


def StrColumn(nullable: bool = False):
    return Column(Text, nullable=nullable)


class GHStar(SQLBase):
    __tablename__ = "star"

    id = IdColumn()
    user = ForeignId("user.id")


class GHReference(SQLBase):
    __tablename__ = "reference"
    id = IdColumn()
    target_kind = IntColumn()
    target = IntColumn()
    entry_kind = IntColumn()
    entry = IntColumn()


class GHEntryKind(IntEnum):
    ISSUE = 1
    PULL = 2
    COMMENT = 3
    COMMIT = 4
    REVIEW_COMMENT = 5


class GHComment(SQLBase):
    __tablename__ = "comment"
    id = IdColumn()
    gh_id = IntColumn()
    index = IntColumn()
    text = StrColumn()
    target_kind = IntColumn()
    target = IntColumn()
    created_at = IntColumn()
    user = IntColumn()


class GHIssueEventKind(IntEnum):
    CLOSED = 1
    LOCKED = 2
    LABELED = 3
    ASSIGNED = 4
    REFERENCED = 5
    SUBSCRIBED = 6
    MERGED = 7
    REOPENED = 8
    HEAD_REF_DELETED = 9
    MENTIONED = 10
    HEAD_REF_RESTORED = 11
    RENAMED = 12
    HEAD_REF_FORCE_PUSHED = 13
    UNLABELED = 14
    BASE_REF_CHANGED = 15
    REVIEW_REQUESTED = 16
    REVIEW_REQUEST_REMOVED = 17
    REVIEW_DISMISSED = 18
    BASE_REF_FORCE_PUSHED = 19
    UNASSIGNED = 20
    UNSUBSCRIBED = 21
    MILESTONED = 22
    COMMENT_DELETED = 23
    READY_FOR_REVIEW = 24
    DEMILESTONED = 25


class GHIssueEvent(SQLBase):
    __tablename__ = "issue_event"
    id = IdColumn()
    actor = ForeignId("user.id", True)
    commit_id = ForeignId("gcommit.id", True)
    created_at = IntColumn()
    event = IntColumn()
    gh_id = IntColumn()
    node_id = StrColumn()
    label = ForeignId("label.id", True)
    assigner = ForeignId("user.id", True)
    review_requester = ForeignId("user.id", True)
    requested_reviewer = ForeignId("user.id", True)
    rename_from = StrColumn(True)
    rename_to = StrColumn(True)
    lock_reason = StrColumn(True)


class GHReviewComment(SQLBase):
    __tablename__ = "review_comment"
    id = IdColumn()
    gh_id = IntColumn()
    in_reply_to = ForeignId("review_comment.id", nullable=True)
    original_commit = ForeignId("gcommit.id", nullable=True)
    original_position = IntColumn()
    diff_hunk = StrColumn()
    created_at = IntColumn()
    target = ForeignId("pull.id")
    commit = ForeignId("gcommit.id", nullable=True)
    user = ForeignId("user.id")


class GHCommit(SQLBase):
    __tablename__ = "gcommit"
    id = IdColumn()
    sha = StrColumn()
    user = ForeignId("user.id", nullable=True)


class GHAssignee(SQLBase):
    __tablename__ = "assignee"
    id = IdColumn()
    user = ForeignId("user.id")
    target = IntColumn()
    target_kind = IntColumn()


class GHUser(SQLBase):
    __tablename__ = "user"

    id = IdColumn()
    name = StrColumn()
    node_id = StrColumn()
    twitter_username = StrColumn()
    bio = StrColumn()
    blog = StrColumn()
    company = StrColumn()
    created_at = IntColumn()
    email = StrColumn()
    followers = IntColumn()
    hireable = Column(Boolean)
    gh_id = IntColumn()
    location = StrColumn()


class GHReactionKind(IntEnum):
    PLUS_ONE = 1
    MINUS_ONE = 2
    LAUGH = 3
    HOORAY = 4
    CONFUSED = 5
    HEART = 6
    ROCKET = 7
    EYES = 8


class GHReaction(SQLBase):
    __tablename__ = "reaction"
    id = IdColumn()
    user = ForeignId("user.id")
    kind = IntColumn()
    created_at = IntColumn()
    target = IntColumn()
    target_kind = IntColumn()


class GHPull(SQLBase):
    __tablename__ = "pull"
    id = IdColumn()
    text = Column(Text)
    title = Column(Text)
    closed_at = IntColumn(nullable=True)
    created_at = IntColumn()
    user = ForeignId("user.id")
    merged_at = IntColumn(nullable=True)
    merged_by = ForeignId("user.id", nullable=True)
    updated_at = IntColumn()

    gh_id = IntColumn()
    number = IntColumn()
    additions = IntColumn()
    deletions = IntColumn()
    changed_files = IntColumn()
    diff_url = StrColumn()
    is_merged = Column(Boolean)
    base_sha = StrColumn()


class GHPullFile(SQLBase):
    __tablename__ = "pull_file"
    id = IdColumn()
    pull = ForeignId("pull.id")
    additions = IntColumn()
    changes = IntColumn()
    deletions = IntColumn()
    filename = StrColumn()
    previous_filename = StrColumn(nullable=True)


class GHPullLabel(SQLBase):
    """
    Single instance of a pull label attached to the database
    """

    __tablename__ = "pull_label"
    id = IdColumn()
    pull = ForeignId("pull.id")
    label = ForeignId("label.id")


class GHLabel(SQLBase):
    """
    Shared github label that can be referred in multiple differen
    instances of `GHPullLabel` etc. throughout the database
    """

    __tablename__ = "label"
    id = IdColumn()
    text = StrColumn()
    description = StrColumn()
    color = StrColumn()


class GHIssue(SQLBase):
    __tablename__ = "issue"
    id = IdColumn()
    gh_id = IntColumn()
    name = StrColumn()
    number = IntColumn()
    user = ForeignId("user.id")
    text = StrColumn()
    closed_at = IntColumn(nullable=True)
    closed_by = ForeignId("user.id", nullable=True)
    updated_at = IntColumn()
    created_at = IntColumn()

    locked = Column(Boolean)
    active_lock_reason = StrColumn(nullable=True)


class GHIssueLabel(SQLBase):
    __tablename__ = "issue_label"
    id = IdColumn()
    issue = ForeignId("issue.id")
    label = ForeignId("label.id")
