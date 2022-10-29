#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Aug 30 14:28:42 2022

@author: haxscramper
"""

# %% Import main modules

import sqlalchemy as sqa
from sqlalchemy import Column, Integer, Text, ForeignKey, Boolean
import re

import argparse
import github as gh
import sys

import logging
from rich.logging import RichHandler

log = None
from enum import IntEnum
from typing import (
    Optional,
    Set,
    Union,
    Any,
)

from sqlalchemy.orm import declarative_base
from tqdm import tqdm
from datetime import datetime as DateTime
from datetime import timezone


SQLBase = declarative_base()

# %% Main state configuration


class State:
    args: argparse.Namespace
    repo: gh.Repository

    known_issues: Set[int] = set()
    known_comments: Set[int] = set()
    known_pulls: Set[int] = set()

    def __init__(self):
        self.last_updated_issue: DateTime = None

    def first_processing(
        self,
        data: Union[
            gh.IssueComment.IssueComment,
            gh.Issue.Issue,
            gh.PullRequest.PullRequest,
        ],
    ) -> bool:
        map_instance = None
        if isinstance(data, gh.IssueComment.IssueComment):
            map_instance = self.known_comments

        elif isinstance(data, gh.Issue.Issue):
            map_instance = self.known_issues

        elif isinstance(data, gh.PullRequest.PullRequest):
            map_instance = self.known_pulls

        result = not (data.id in map_instance)
        map_instance.add(data.id)
        if result and isinstance(data, gh.Issue.Issue):
            self.last_updated_issue = data.updated_at

        return result

    def is_wanted_issue(self, issue: gh.Issue.Issue) -> bool:
        return (
            (not self.last_updated_issue)
            or self.last_updated_issue < issue.updated_at
            or self.first_processing(issue)
        )

    def rebuild_cache(self, session):
        for issue in session.query(GHIssue):
            self.known_issues.add(issue.gh_id)
            updated = DateTime.fromtimestamp(issue.updated_at)
            if (
                not self.last_updated_issue
            ) or self.last_updated_issue < updated:
                self.last_updated_issue = updated

        for comment in session.query(GHComment):
            self.known_comments.add(comment.gh_id)


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


def event_name_to_kind(event: str) -> GHIssueEventKind:
    match event:
        case "locked":
            return GHIssueEventKind.LOCKED

        case "labeled":
            return GHIssueEventKind.LABELED

        case "assigned":
            return GHIssueEventKind.ASSIGNED

        case "referenced":
            return GHIssueEventKind.REFERENCED

        case "subscribed":
            return GHIssueEventKind.SUBSCRIBED

        case "closed":
            return GHIssueEventKind.CLOSED

        case "merged":
            return GHIssueEventKind.MERGED

        case "reopened":
            return GHIssueEventKind.REOPENED

        case "head_ref_deleted":
            return GHIssueEventKind.HEAD_REF_DELETED

        case "mentioned":
            return GHIssueEventKind.MENTIONED

        case "head_ref_restored":
            return GHIssueEventKind.HEAD_REF_RESTORED

        case "head_ref_force_pushed":
            return GHIssueEventKind.HEAD_REF_FORCE_PUSHED

        case "renamed":
            return GHIssueEventKind.RENAMED

        case "unlabeled":
            return GHIssueEventKind.UNLABELED

        case "base_ref_changed":
            return GHIssueEventKind.BASE_REF_CHANGED

        case "review_requested":
            return GHIssueEventKind.REVIEW_REQUESTED

        case "review_request_removed":
            return GHIssueEventKind.REVIEW_REQUEST_REMOVED

        case "review_dismissed":
            return GHIssueEventKind.REVIEW_DISMISSED

        case "milestoned":
            return GHIssueEventKind.MILESTONED

        case "base_ref_force_pushed":
            return GHIssueEventKind.BASE_REF_FORCE_PUSHED

        case "unassigned":
            return GHIssueEventKind.UNASSIGNED

        case "unsubscribed":
            return GHIssueEventKind.UNSUBSCRIBED

        case _:
            assert False, event

def reaction_name_to_kind(reaction: str) -> GHReactionKind:
    match reaction:
        case "+1":
            return GHReactionKind.PLUS_ONE

        case "-1":
            return GHReactionKind.MINUS_ONE

        case "laugh":
            return GHReactionKind.LAUGH

        case "hooray":
            return GHReactionKind.HOORAY

        case "confused":
            return GHReactionKind.CONFUSED

        case "heart":
            return GHReactionKind.HEART

        case "rocket":
            return GHReactionKind.ROCKET

        case "eyes":
            return GHReactionKind.EYES

        case _:
            assert False, reaction


class Connect:
    engine: sqa.engine.Engine
    session: sqa.orm.Session
    meta: sqa.MetaData
    state: State
    con: sqa.engine.Connection

    def __init__(self):
        self.commit_cache = {}

    def add(self, value: Any) -> int:
        self.session.add(value)
        self.session.commit()
        self.session.flush()
        assert value.id
        return value.id

    def table(self, name):
        return self.meta.tables[name]

    def get_last_updated_pull(self):
        next(self.con.execute(
            sqa.select(self.table("pull")).
              order_by(GHPull.updated_at.desc())
        ))

    def get_from_github_id(self, gh_id, table):
        """
        Return a DB pull ID (if stores) from github ID,
        otherwise return `None`
        """
        res = [it for it in self.con.execute(
            sqa.select(self.table(table)).where(
                self.table(table).c.gh_id == gh_id
            )
        )]

        if len(res) == 0:
            return None

        else:
            if 1 < len(res):
                log.error(
                    f"{table} {gh_id} has more than one stored counterpart")

            return res[0]


    def get_label_by_name(self, name):
        res = [it for it in self.con.execute(
            sqa.select(self.table("label")).where(
                self.table("label").c.text == name
            )
        )]

        if len(res) == 0:
            return None

        else:
            return res[0]

    def get_user_by_name(self, name):
        res = [it for it in self.con.execute(
            sqa.select(self.table("user")).where(
                self.table("user").c.name == name
            )
        )]

        if len(res) == 0:
            return None

        else:
            return res[0]

    def get_pull_by_id(self, gh_id):
       return self.get_from_github_id(gh_id, "pull")

    def get_issue_by_id(self, gh_id):
       return self.get_from_github_id(gh_id, "issue")

    def reference_issue(self, entry_id, entry_kind, number):
        """
        Add reference to a github issue from the same repository
        """
        for issue in self.con.execute(
            sqa.select(self.meta.tables["issue"]).where(
                self.meta.tables["issue"].c.number == number
            )
        ):
            self.add(
                GHReference(
                    target_kind=GHEntryKind.ISSUE,
                    target=issue.id,
                    entry=entry_id,
                    entry_kind=entry_kind,
                )
            )

    def reference_pull(self, entry_id, entry_kind, number):
        """
        Reference a pull request from the same repository
        """
        for issue in self.con.execute(
            sqa.select(self.meta.tables["pull"]).where(
                self.meta.tables["pull"].c.number == number
            )
        ):
            self.add(
                GHReference(
                    target_kind=GHEntryKind.PULL,
                    target=issue.id,
                    entry=entry_id,
                    entry_kind=entry_kind,
                )
            )

    def reference_commit(self, entry_id, entry_kind, number):
        commit = self.get_commit(number)
        if commit:
            self.add(
                GHReference(
                    target_kind=GHEntryKind.COMMIT,
                    target=commit,
                    entry=entry_id,
                    entry_kind=entry_kind,
                )
            )

    def fill_mentions(self, entry_id, entry_kind: GHEntryKind, text: str):
        for match in re.findall(r"[\da-f]{7,40}", text):
            self.reference_commit(entry_id, entry_kind, match)

        for (owner, repo, kind, number) in re.findall(
            r"https?://github\.com/([^\\]+?)/([^\\]+?)/(issues|pulls|commit)/(\d+).*",
            text,
        ):
            if kind == "issues":
                self.reference_issue(entry_id, entry_kind, int(number))

            elif kind == "pulls":
                self.reference_pull(entry_id, entry_kind, int(number))

            elif kind == "commit":
                self.reference_commit(entry_id, entry_kind, number)

        for number in re.findall(r"#(\d+)", text):
            self.reference_issue(entry_id, entry_kind, int(number))
            self.reference_pull(entry_id, entry_kind, int(number))

    def get_user(self, user: gh.NamedUser.NamedUser) -> int:
        stored = self.get_user_by_name(user.login)
        if stored:
            # log.debug(f"Cached user data {user.login}")
            return stored.id

        else:
            return self.add(
                GHUser(
                    name=user.login,
                    node_id=user.node_id,
                    twitter_username=user.twitter_username or "",
                    bio=user.bio or "",
                    blog=user.blog or "",
                    created_at=to_stamp(user.created_at),
                    company=user.company or "",
                    email=user.email or "",
                    followers=user.followers,
                    hireable=user.hireable,
                    gh_id=user.id,
                    location=user.location or "",
                )
            )


    def get_commit(self, sha: str) -> Optional[int]:
        if sha not in self.commit_cache:
            try:
                commit = self.state.repo.get_commit(sha)
            except gh.GithubException:
                return None

            if commit.sha not in self.commit_cache:
                self.commit_cache[commit.sha] = self.add(
                    GHCommit(
                        sha=commit.sha,
                        user=commit.committer and
                             self.get_user(commit.committer),
                    )
                )

            self.commit_cache[sha] = self.commit_cache[commit.sha]

        return self.commit_cache[sha]

    def get_issue(self, issue: gh.Issue.Issue) -> int:
        stored = self.get_issue_by_id(issue.id)
        if stored:
            # log.debug("Getting issue ID from the stored cache")
            return stored.id

        else:
            log.info(f"Issue {issue.number} [red]" + issue.title + "[/]")
            # log.debug({
            #     "created": issue.created_at,
            #     "id": issue.id,
            #     "url": issue.url
            # })

            issue_id = self.add(
                GHIssue(
                    name=issue.title or "",
                    gh_id=issue.id,
                    user=self.get_user(issue.user),
                    closed_by=issue.closed_by and self.get_user(
                        issue.closed_by),
                    created_at=to_stamp(issue.created_at),
                    updated_at=to_stamp(issue.updated_at),
                    closed_at=to_stamp(issue.closed_at),
                    locked=issue.locked,
                    active_lock_reason=issue.active_lock_reason,
                    text=issue.body or "",
                    number=issue.number,
                )
            )

            if issue.body:
                self.fill_mentions(issue_id, GHEntryKind.ISSUE, issue.body)

            for index, comment in enumerate(issue.get_comments()):
                comment_id = self.add(
                    GHComment(
                        gh_id=comment.id,
                        target=issue_id,
                        index=index,
                        target_kind=int(GHEntryKind.ISSUE),
                        user=self.get_user(comment.user),
                        created_at=to_stamp(comment.created_at),
                        text=comment.body or "",
                    )
                )

                self.fill_mentions(
                    comment_id, GHEntryKind.COMMENT, comment.body
                )

            for label in issue.labels:
                label_id = self.get_label(label)
                self.add(GHIssueLabel(issue=issue_id, label=label_id))

            for reaction in issue.get_reactions():
                self.add(
                    GHReaction(
                        target = issue_id,
                        target_kind = GHEntryKind.ISSUE,
                        created_at = to_stamp(reaction.created_at),
                        user = self.get_user(reaction.user),
                        kind = reaction_name_to_kind(reaction.content)
                    )
                )

            for assignee in issue.assignees:
                self.add(
                    GHAssignee(
                        target=issue_id,
                        target_kind=int(GHEntryKind.ISSUE),
                        user=self.get_user(assignee),
                    )
                )

            return issue_id

    def get_stored_pull_id(self, pull: gh.PullRequest.PullRequest) -> int:
        stored = self.get_pull_by_id(pull.id)
        if stored:
            log.info(f"Cached pull {pull.number} [red]{pull.title}[/]")
            return stored.id

        else:
            return None

    def get_pull(self, pull: gh.PullRequest.PullRequest) -> int:
        stored = self.get_pull_by_id(pull.id)
        if stored:
            return stored.id

        else:
            log.info(f"Pull {pull.number} [red]" + pull.title + "[/]")
            # log.debug({
            #     "created": pull.created_at,
            #     "id": pull.id,
            #     "url": pull.url
            # })

            gh_pull = GHPull(
                text=pull.body or "",
                title=pull.title or "",
                closed_at=to_stamp(pull.closed_at),
                created_at=to_stamp(pull.created_at),
                user = pull.user and self.get_user(pull.user),

                merged_at=to_stamp(pull.merged_at),
                merged_by=pull.merged_by and self.get_user(pull.merged_by),

                updated_at=to_stamp(pull.updated_at),

                gh_id=pull.id,
                additions=pull.additions,
                deletions=pull.deletions,
                changed_files=pull.changed_files,
                number=pull.number,
                diff_url=pull.diff_url,
                is_merged=pull.is_merged(),
                base_sha=pull.base.sha,
            )

            pull_id = self.add(gh_pull)

            if pull.body:
                self.fill_mentions(pull_id, GHEntryKind.PULL, pull.body)

            for label in pull.labels:
                label_id = self.get_label(label)
                self.add(GHPullLabel(pull=pull_id, label=label_id))

            for event in pull.get_issue_events():
                self.add(
                    GHIssueEvent(
                        gh_id=event.id,
                        actor=event.actor and self.get_user(event.actor),
                        commit_id=event.commit_id
                        and self.get_commit(event.commit_id),
                        created_at=to_stamp(event.created_at),
                        event=int(event_name_to_kind(event.event)),
                        node_id=event.node_id,
                        label=event.label and self.get_label(event.label),
                        assigner=event.assigner
                        and self.get_user(event.assigner),
                        review_requester=event.review_requester
                        and self.get_user(event.review_requester),
                    )
                )

            for file in pull.get_files():
                # TODO Use file IDs, move names into secondary directory.
                log.debug(f"Edited {file.filename}")
                self.add(
                    GHPullFile(
                        pull=pull_id,
                        additions=file.additions,
                        changes=file.changes,
                        deletions=file.deletions,
                        filename=file.filename,
                        previous_filename=file.previous_filename
                    )
                )

            for index, comment in enumerate(pull.get_issue_comments()):
                comment_id = self.add(
                    GHComment(
                        gh_id=comment.id,
                        target=pull_id,
                        index=index,
                        target_kind=int(GHEntryKind.PULL),
                        user=self.get_user(comment.user),
                        created_at=to_stamp(comment.created_at),
                        text=comment.body,
                    )
                )

                self.fill_mentions(
                    comment_id, GHEntryKind.COMMENT, comment.body
                )

            if False:
                # HACK temporarily disabled because old database did not
                # have nullable constraint enabled.
                for comment in pull.get_review_comments():
                    review = GHReviewComment(
                        gh_id=comment.id,
                        target=pull_id,
                        user=self.get_user(comment.user),
                        created_at=to_stamp(comment.created_at),
                        diff_hunk=comment.diff_hunk,
                        commit=self.get_commit(comment.commit_id),
                        original_commit=self.get_commit(
                            comment.original_commit_id
                        ),
                    )

                    print(review)
                    comment_id = self.add(review)

                    self.fill_mentions(
                        comment_id, GHEntryKind.REVIEW_COMMENT, comment.body
                    )

    def get_label(self, label: gh.Label.Label) -> int:
        stored = self.get_label_by_name(label.name)
        if stored:
            return stored.id

        else:
            return self.add(
                GHLabel(
                    text=label.name,
                    description="FIXME", # HACK. Trying to get
                    # description=label.description, causes the '400
                    # returned object contains no URL' error
                    color=label.color,
                )
            )


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--token",
        dest="token",
        default=None,
        help="Github Access token string",
    )

    parser.add_argument(
        "--repo",
        dest="repo",
        default=None,
        help="Github repository name in form of user/repo"
    )

    parser.add_argument(
        "--clean-write",
        dest="clean_write",
        default=None,
        help="Create database from scratch, dropping all tables and "
        + "rewriting the ",
    )

    parser.add_argument(
        "--max-issue-fetch",
        dest="max_issues_fetch",
        default=5,
        type=int,
        help="Maximum number of issues to fetch in a single program run",
    )

    parser.add_argument(
        "--max-pull-fetch",
        dest="max_pulls_fetch",
        default=5,
        type=int,
        help="Maximum number of pull requests to fetch in a single program run",
    )

    parser.add_argument(
        "outfile", default=None, help="Output database file"
    )

    return parser.parse_args(args)


# %% Reading the data from the GitHub repository


def to_stamp(date_time: DateTime) -> Optional[int]:
    if date_time:
        return int(date_time.replace(tzinfo=timezone.utc).timestamp())

    else:
        return None


def fill_stargazers(s: State):
    for star in s.repo.get_stargazers_with_dates():
        pass


def fill_issues(c: Connect):
    s = c.state
    last = s.last_updated_issue
    issues = s.repo.get_issues(
        state="all",
        sort="updated",
        direction="asc",
        since=last or gh.GithubObject.NotSet,
    )

    count = 0
    for issue in issues:
        # HACK this check is necessary because `get_issues` consistently
        # returns pull request URLs as well and they even manage to pass
        # into the API, returning valid responses.
        if issue.html_url.endswith(f"issues/{issue.number}") \
           and s.is_wanted_issue(issue):
            c.get_issue(issue)
            count += 1

            if s.args.max_issues_fetch < count:
                break


def fill_pulls(c: Connect):
    s = c.state
    pulls = s.repo.get_pulls(
        state="all",
        direction="asc",
        sort="updated"
    )

    count = 1
    for pull in pulls:
        # HACK same hack reason as in `fill_issues`
        if pull.html_url.endswith(f"pull/{pull.number}"):
            stored = c.get_stored_pull_id(pull)
            if stored:
                continue

            c.get_pull(pull)

            count += 1
            if s.args.max_pulls_fetch < count:
                log.warning(
                    f"Reached max number of pulls ({count}), withdrawing")

                break

        else:
            log.debug({
                "url": pull.html_url,
                "num": pull.number
            })


def impl(args):
    if not args.token:
        with open("github-access-token", "r") as f:
            args.token = f.read().replace("\n", "")

    g = gh.Github(args.token)
    repo = g.get_repo(args.repo)
    s = State()
    c = Connect()
    c.state = s
    s.repo = repo
    s.args = args
    c.engine = sqa.create_engine(f"sqlite:///{args.outfile}")
    Session = sqa.orm.sessionmaker(bind=c.engine)
    c.session = Session()
    c.meta = SQLBase.metadata
    c.con = c.engine.connect()

    logging.basicConfig(
        level="NOTSET",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(
            rich_tracebacks=True,
            markup=True
        )],
    )

    for name in logging.root.manager.loggerDict:
        logger = logging.getLogger(name)
        logger.setLevel(logging.WARNING)

    global log
    log = logging.getLogger("rich")
    log.setLevel(logging.DEBUG)

    if args.clean_write:
        SQLBase.metadata.drop_all(c.engine)

    SQLBase.metadata.create_all(c.engine)
    c.session.commit()

    s.rebuild_cache(c.session)
    try:
        fill_issues(c)
        fill_pulls(c)

    finally:
        c.session.commit()
        c.session.close()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        impl(
            parse_args(
                [
                    "parse_github.sqlite",
                    "--max-issue-fetch=1000",
                    "--max-pull-fetch=1000",
                    # "--clean-write=True",
                    "--repo=nim-lang/Nim"
                ]
            )
        )
    else:
        impl(parse_args())

    print("analysis done")
