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
import sqlite3
import sys

from pydantic import BaseModel
from enum import IntEnum
from typing import (
    List,
    Type,
    Generic,
    TypeVar,
    Dict,
    Tuple,
    Optional,
    Set,
    Union,
)

from sqlalchemy.orm import declarative_base
from tqdm import tqdm
from datetime import datetime as DateTime
from datetime import timezone


print("Created new SQL Base")
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
        result = True
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


class GHCommit(SQLBase):
    __tablename__ = "gcommit"
    id = IdColumn()
    sha = StrColumn()
    user = ForeignId("user.id")


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


class GHPull(SQLBase):
    __tablename__ = "pull"
    id = IdColumn()
    text = Column(Text)
    closed_at = IntColumn(nullable=True)
    created_at = IntColumn()
    gh_id = IntColumn()
    number = IntColumn()
    additions = IntColumn()
    deletions = IntColumn()
    changed_files = IntColumn()
    diff_url = StrColumn()
    is_merged = Column(Boolean)
    base_sha = StrColumn()


class GHPullLabel(SQLBase):
    __tablename__ = "pull_label"
    id = IdColumn()
    pull = ForeignId("pull.id")
    label = ForeignId("label.id")


class GHLabel(SQLBase):
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
    url = StrColumn()
    number = IntColumn()
    user = ForeignId("user.id")
    text = StrColumn()
    closed_at = IntColumn(nullable=True)
    updated_at = IntColumn()
    created_at = IntColumn()


class GHIssueLabel(SQLBase):
    __tablename__ = "issue_label"
    id = IdColumn()
    issue = ForeignId("issue.id")
    label = ForeignId("label.id")


class Connect:
    engine: sqa.engine.Engine
    session: sqa.orm.Session
    meta: sqa.MetaData
    state: State

    def __init__(self):
        self.user_cache = {}
        self.label_cache = {}
        self.commit_cache = {}
        self.issue_cache = {}
        self.pull_cache = {}

    def add(self, value) -> int:
        self.session.add(value)
        self.session.flush()
        assert value.id
        return value.id

        tables = self.meta.tables

    def reference_issue(self, entry_id, entry_kind, number):
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
        commit = self.add_commit(number)
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
        s = self.state

        for match in re.findall(r"[0-9a-f]{7,40}", text):
            self.reference_commit(entry_id, entry_kind, match)

        for (owner, repo, kind, number) in re.findall(
            r"https?://github\.com/([^\\]+?)/([^\\]+?)/(issues|pulls|commit)/([^\s]+)",
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

    def add_user(self, user: GHUser | gh.NamedUser.NamedUser) -> int:
        if isinstance(user, gh.NamedUser.NamedUser):
            return self.add_user(
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

        else:
            if user.name not in self.user_cache:
                self.user_cache[user.name] = self.add(user)

            return self.user_cache[user.name]

    def add_commit(self, sha: str) -> Optional[int]:
        if sha not in self.commit_cache:
            try:
                commit = self.state.repo.get_commit(sha)
            except gh.GithubException:
                return None

            if commit.sha not in self.commit_cache:
                self.commit_cache[commit.sha] = self.add(
                    GHCommit(
                        sha=commit.sha, user=self.add_user(commit.committer)
                    )
                )

            self.commit_cache[sha] = self.commit_cache[commit.sha]

        return self.commit_cache[sha]

    def add_issue(self, issue: GHIssue | gh.Issue.Issue) -> int:
        if isinstance(issue, gh.Issue.Issue):
            if issue.id in self.issue_cache:
                return self.issue_cache[issue.id]

            issue_id = self.add_issue(
                GHIssue(
                    name=issue.title,
                    gh_id=issue.id,
                    user=self.add_user(issue.user),
                    created_at=to_stamp(issue.created_at),
                    updated_at=to_stamp(issue.updated_at),
                    closed_at=to_stamp(issue.closed_at),
                    url=issue.url,
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
                        user=self.add_user(comment.user),
                        created_at=to_stamp(comment.created_at),
                        text=comment.body or "",
                    )
                )

                self.fill_mentions(
                    comment_id, GHEntryKind.COMMENT, comment.body
                )

            for label in issue.labels:
                label_id = self.add_label(label)
                self.add(GHIssueLabel(issue=issue_id, label=label_id))

            for assignee in issue.assignees:
                self.add(
                    GHAssignee(
                        target=issue_id,
                        target_kind=int(GHEntryKind.ISSUE),
                        user=self.add_user(assignee),
                    )
                )

            return issue_id

        else:
            if issue.gh_id not in self.issue_cache:
                self.issue_cache[issue.gh_id] = self.add(issue)

            return self.issue_cache[issue.gh_id]

    def add_label(self, label: GHLabel | gh.Label.Label) -> int:
        if isinstance(label, gh.Label.Label):
            return self.add_label(
                GHLabel(
                    text=label.name,
                    description=label.description,
                    color=label.color,
                )
            )

        else:
            if label.text not in self.label_cache:
                self.label_cache[label.text] = self.add(label)

            return self.label_cache[label.text]


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--token",
        dest="token",
        default=None,
        help="Github Access token string",
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

    parser.add_argument("outfile", default=None, help="Output database file")

    return parser.parse_args(args)


# %% Reading the data from the github repository


def progress(size: int) -> tqdm:
    return tqdm(total=size, bar_format="{l_bar}{bar:40}{r_bar}{bar:-10b}")


def to_stamp(date_time: DateTime) -> int:
    return date_time and date_time.replace(tzinfo=timezone.utc).timestamp()


def fill_stargazers(s: State):
    with progress(s.repo.stargazers_count) as bar:
        for star in s.repo.get_stargazers_with_dates():
            bar.update()


def fill_issues(c: Connect):
    s = c.state
    last = s.last_updated_issue
    issues = s.repo.get_issues(
        state="all",
        sort="updated",
        direction="asc",
        since=last or gh.GithubObject.NotSet,
    )

    with progress(issues.totalCount) as bar:
        count = 0
        for issue in issues:
            if s.is_wanted_issue(issue):
                c.add_issue(issue)
                count += 1

                if s.args.max_issues_fetch < count:
                    break

            bar.update()


def fill_pulls(c: Connect):
    s = c.state
    pulls = s.repo.get_pulls(state="all", direction="asc", sort="updated")
    count = 1
    with progress(pulls.totalCount) as bar:
        for pull in pulls:
            if s.first_processing(pull):
                pull_id = c.add(
                    GHPull(
                        text=pull.body or "",
                        closed_at=to_stamp(pull.closed_at),
                        created_at=to_stamp(pull.created_at),
                        gh_id=pull.id,
                        additions=pull.additions,
                        deletions=pull.deletions,
                        changed_files=pull.changed_files,
                        number=pull.number,
                        diff_url=pull.diff_url,
                        is_merged=pull.is_merged(),
                        base_sha=pull.base.sha,
                    )
                )

                if pull.body:
                    c.fill_mentions(pull_id, GHEntryKind.PULL, pull.body)

                for label in pull.labels:
                    label_id = c.add_label(label)
                    c.add(GHPullLabel(pull=pull_id, label=label_id))

                for index, comment in enumerate(pull.get_comments()):
                    comment_id = c.add(
                        GHComment(
                            gh_id=comment.id,
                            target=pull_id,
                            index=index,
                            target_kind=int(GHEntryKind.PULL),
                            user=c.add_user(comment.user),
                            created_at=to_stamp(comment.created_at),
                            text=comment.body,
                        )
                    )

                    c.fill_mentions(
                        comment_id, GHEntryKind.COMMENT, comment.body
                    )

            count += 1
            if s.args.max_pulls_fetch < count:
                break

            bar.update()


def impl(args):
    if not args.token:
        with open("github-access-token", "r") as f:
            args.token = f.read().replace("\n", "")

    g = gh.Github(args.token)
    repo = g.get_repo("haxscramper/test")
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
                    "--max-issue-fetch=10",
                    "--clean-write=True",
                ]
            )
        )
    else:
        impl(parse_args())
