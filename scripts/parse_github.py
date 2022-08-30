#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Aug 30 14:28:42 2022

@author: haxscramper
"""

# %% Import main modules

import sqlalchemy as sqa
from sqlalchemy import Column, Integer, Text, ForeignKey

import argparse
import github as gh
import sqlite3
import sys

from pydantic import BaseModel
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

    def __init__(self):
        self.last_updated_issue: DateTime = None

    def first_processing(
        self, data: Union[gh.IssueComment.IssueComment, gh.Issue.Issue]
    ) -> bool:
        result = True
        map_instance = None
        if isinstance(data, gh.IssueComment):
            map_instance = self.known_comments

        elif isinstance(data, gh.Issue):
            map_instance = self.known_issues

        result = data.gh_id in map_instance
        map_instance.add(data.gh_id)
        if result and isinstance(data, gh.Issue):
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


class GHStar(SQLBase):
    __tablename__ = "star"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user = Column(Integer, ForeignKey("user.id"))


class GHMentionUser(SQLBase):
    __tablename__ = "mention_user"
    id = Column(Integer, primary_key=True, autoincrement=True)
    comment = Column(Integer, ForeignKey("comment.id"))
    user = Column(Integer, ForeignKey("user.id"))


class GHMentionEntry(SQLBase):
    __tablename__ = "mention_entry"
    id = Column(Integer, primary_key=True, autoincrement=True)
    comment = Column(Integer, ForeignKey("comment.id"))
    entry_type = Column(Integer)
    entry_gh_id = Column(Integer)


class GHComment(SQLBase):
    __tablename__ = "comment"
    id = Column(Integer, primary_key=True, autoincrement=True)
    gh_id = Column(Integer)
    index = Column(Integer)
    text = Column(Text)
    issue = Column(Integer, ForeignKey("issue.id"))
    created_at = Column(Integer)
    user = Column(Integer)


class GHUser(SQLBase):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text)


class GHLabel(SQLBase):
    __tablename__ = "label"
    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(Text)
    description = Column(Text)


class GHIssue(SQLBase):
    __tablename__ = "issue"
    id = Column(Integer, primary_key=True, autoincrement=True)
    gh_id = Column(Integer)
    name = Column(Text)
    url = Column(Text)
    user = Column(Integer, ForeignKey("user.id"))
    closed_at = Column(Integer)
    updated_at = Column(Integer)
    created_at = Column(Integer)


class GHIssueLabels(SQLBase):
    __tablename__ = "issue_label"
    id = Column(Integer, primary_key=True, autoincrement=True)
    issue_id = Column(Integer, ForeignKey("issue.id"))
    label_id = Column(Integer, ForeignKey("label.id"))


class GHIssueAssignee(SQLBase):
    __tablename__ = "issue_assignee"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user = Column(Integer, ForeignKey("user.id"))


class Connect:
    engine: sqa.engine.Engine
    session: sqa.orm.Session
    state: State

    def __init__(self):
        self.user_cache = {}
        self.label_cache = {}

    def add(self, value) -> int:
        self.session.add(value)
        self.session.flush()
        assert value.id
        return value.id

    def add_user(self, user: GHUser | gh.NamedUser.NamedUser) -> int:
        if isinstance(user, gh.NamedUser.NamedUser):
            return self.add_user(GHUser(name=user.login))

        else:
            if user.name not in self.user_cache:
                self.user_cache[user.name] = self.add(user)

            return self.user_cache[user.name]

    def add_label(self, label: GHLabel | gh.Label.Label) -> int:
        if isinstance(label, gh.Label.Label):
            return self.add_label(
                GHLabel(text=label.name, description=label.description)
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
                issue_id = c.add(
                    GHIssue(
                        name=issue.title,
                        gh_id=issue.id,
                        user=c.add_user(issue.user),
                        created_at=to_stamp(issue.created_at),
                        updated_at=to_stamp(issue.updated_at),
                        closed_at=to_stamp(issue.closed_at),
                        url=issue.url,
                    )
                )

                for index, comment in enumerate(issue.get_comments()):
                    c.add(
                        GHComment(
                            gh_id=comment.id,
                            issue=issue_id,
                            index=index,
                            user=c.add_user(comment.user),
                            created_at=to_stamp(comment.created_at),
                            text=comment.body,
                        )
                    )

                for label in issue.labels:
                    c.add_label(label)

                count += 1

                if s.args.max_issues_fetch < count:
                    break

            bar.update()


def impl(args):
    if not args.token:
        with open("github-access-token", "r") as f:
            args.token = f.read().replace("\n", "")

    g = gh.Github(args.token)
    repo = g.get_repo("nim-lang/Nim")
    s = State()
    c = Connect()
    c.state = s
    s.repo = repo
    s.args = args
    c.engine = sqa.create_engine(f"sqlite:///{args.outfile}")
    Session = sqa.orm.sessionmaker(bind=c.engine)
    c.session = Session()

    if args.clean_write:
        SQLBase.metadata.drop_all(c.engine)

    SQLBase.metadata.create_all(c.engine)
    c.session.commit()

    s.rebuild_cache(c.session)
    try:
        fill_issues(c)

    finally:
        c.session.commit()
        c.session.close()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        impl(parse_args(["/tmp/tmp.sqlite", "--max-issue-fetch=5"]))
    else:
        impl(parse_args())
