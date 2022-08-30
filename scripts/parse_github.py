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
from typing import List, Type, Generic, TypeVar, Dict, Tuple, Optional, Set
from sqlalchemy.orm import declarative_base
from tqdm import tqdm
from datetime import datetime as DateTime
from datetime import timezone

SQLBase = declarative_base()

# %% Define data-oriented design base types


class DODId:
    __value__: int

    def __init__(self, value: int = -1):
        self.__value__ = value + 1

    def idx(self) -> int:
        return self.__value__ - 1

    def is_nil(self) -> bool:
        return self.__value__ == 0

    def value(self) -> int:
        return self.__value__

    def __repr__(self) -> str:
        if self.is_nil():
            return f"{self.__class__.__name__}(<nil>)"

        else:
            return f"{self.__class__.__name__}({self.value()})"


Val = TypeVar("T")
Id = TypeVar("Id", bound="DODId")


class DODStore(Generic[Id, Val]):
    store: List[Val]
    __IdType__: Type[Id]
    __ValType__: Type[Val]

    def __init__(self, IdType: Type[Id], ValType: Type[Val]):
        self.__ValType__ = ValType
        self.__IdType__ = IdType
        self.store = []

    def add(self, value: Val) -> Id:
        assert isinstance(
            value, self.__ValType__
        ), f"Expected {self.__ValType__} for value but found {type(value)}"

        result = len(self.store)
        self.store.append(value)
        return self.__IdType__(result)

    def get(self, id: Id) -> Val:
        return self.store[id.idx()]

    def __len__(self) -> int:
        return len(self.store)

    def pairs(self) -> Tuple[Id, Val]:
        for idx, value in enumerate(self.store):
            assert isinstance(
                value, self.__ValType__
            ), f"Expected {self.__ValType__} for value but found {type(value)}"
            yield (self.__IdType__(idx), value)


class DODInternStore(Generic[Id, Val]):
    __store__: DODStore[Id, Val]

    def __init__(self, IdType: Type[Id], ValType: Type[Val]):
        self.__store__ = DODStore[Id, Val](IdType, ValType)
        self.__map__ = {}

    def __len__(self) -> int:
        return len(self.__store__)

    def add(self, value: Val) -> Id:
        if value not in self.__map__:
            self.__map__[value] = self.__store__.add(value)

        return self.__map__[value]

    def get(self, id: Id) -> Val:
        return self.__store__.get(id)

    def pairs(self) -> Tuple[Id, Val]:
        for id, val in self.__store__.pairs():
            yield (id, val)

    def __contains__(self, value: Val):
        return value in self.__map__


# %% Defined DOD mapping types - IDs and values

# %%% ID types


class GHUserId(DODId):
    pass


class GHStarId(DODId):
    pass


class GHIssueId(DODId):
    pass


class GHCommentId(DODId):
    pass


class GHLabelId(DODId):
    pass


# %%% Value types


class ValidatingModel(BaseModel):
    class Config:
        arbitrary_types_allowed = True
        validate_assignment = True


class GHUser(ValidatingModel):
    name: str

    def __hash__(self):
        return hash(self.name)


class GHStar(ValidatingModel):
    user: GHUserId
    time: DateTime


class GHReference(ValidatingModel):
    pass


class GHComment(ValidatingModel):
    user: GHUserId
    text: str
    created_at: DateTime


class GHIssue(ValidatingModel):
    title: str
    gh_id: int
    user: GHUserId
    created_at: DateTime
    updated_at: DateTime
    url: str
    closed_at: Optional[DateTime] = None
    comments: List[GHComment] = []
    assignees: List[GHUserId] = []
    labels: List[GHLabelId] = []
    # milestone: TODO


class GHLabel(ValidatingModel):
    name: str


# %%% Main DOD store object


class GHStore:
    users = DODInternStore[GHUserId, GHUser](GHUserId, GHUser)
    issues = DODStore[GHIssueId, GHIssue](GHIssueId, GHIssue)
    comments = DODStore[GHCommentId, GHComment](GHCommentId, GHComment)
    labels = DODInternStore[GHLabelId, GHLabel](GHLabelId, GHLabel)

    def add_user(self, user: GHUser | gh.NamedUser.NamedUser) -> GHUserId:
        start_size = len(self.issues)
        _id = GHUserId()
        if isinstance(user, GHUser):
            _id = self.users.add(user)
        else:
            fastkey = GHUser(name=user.login)
            if fastkey in self.users:
                _id = self.users.add(fastkey)

            else:
                fastkey = GHUser(
                    name=user.login,  # TODO add more fields
                )

                _id = self.users.add(fastkey)

        assert len(self.issues) == start_size

        return _id

    def add_issue(self, issue: GHIssue) -> GHIssueId:
        _id = self.issues.add(issue)
        return _id

    def add_comment(self, comment: GHComment) -> GHCommentId:
        _id = self.comments.add(comment)
        return _id


# %% Main state configuration


class State:
    args: argparse.Namespace
    repo: gh.Repository
    store = GHStore()
    
    known_issues: Set[int] = set()
    known_comments: Set[int] = set()
    
    def first_processing(self, data: gh.IssueComment | gh.Issue) -> bool:
        result = True
        map_instance = None
        if isinstance(data, gh.IssueComment):
            map_instance = self.known_comments
            
        elif isinstance(data, gh.Issue):
            map_instance = self.known_issues
            
        result = data.id in map_instance
        map_instance.add(data.id)
        return result
            


class Connect:
    engine: sqa.engine.Engine
    session: sqa.orm.Session


def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--token",
        dest="token",
        default=None,
        help="Github Access token string",
    )

    parser.add_argument("outfile", default=None, help="Output database file")

    return parser.parse_args(args)


# %% Reading the data from the github repository


def progress(size: int) -> tqdm:
    return tqdm(total=size, bar_format="{l_bar}{bar:40}{r_bar}{bar:-10b}")


def fill_stargazers(s: State):
    with progress(s.repo.stargazers_count) as bar:
        for star in s.repo.get_stargazers_with_dates():
            bar.update()


def fill_issues(s: State):
    issues = s.repo.get_issues()
    with progress(issues.totalCount) as bar:
        count = 0
        for issue in issues:
            issue_id = s.store.add_issue(
                GHIssue(
                    title=issue.title,
                    gh_id=issue.id,
                    user=s.store.add_user(issue.user),
                    created_at=issue.created_at,
                    updated_at=issue.updated_at,
                    url=issue.url,
                )
            )

            for comment in issue.get_comments():
                s.store.issues.get(issue_id).comments.append(
                    s.store.add_comment(
                        GHComment(
                            user=s.store.add_user(comment.user),
                            created_at=comment.created_at,
                            text=comment.body,
                        )
                    )
                )

            count += 1

            bar.update()

            if 10 < count:
                break


# %% Implementation entry point

# %%% Define mapping of the DOD types to the ORM


class GHStarORM(SQLBase):
    __tablename__ = "star"

    id = Column(Integer, primary_key=True)
    user = Column(Integer)


class GHCommentORM(SQLBase):
    __tablename__ = "comment"
    id = Column(Integer, primary_key=True)
    gh_id = Column(Integer)
    index = Column(Integer)
    text = Column(Text)
    created_at = Column(Integer)
    user = Column(Integer)


class GHUserORM(SQLBase):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True)
    name = Column(Text)


class GHLabel(SQLBase):
    __tablename__ = "label"
    id = Column(Integer, primary_key=True)
    text = Column(Text)


class GHIssueORM(SQLBase):
    __tablename__ = "issue"
    id = Column(Integer, primary_key=True)
    gh_id = Column(Integer)
    name = Column(Text)
    user = Column(Integer, ForeignKey("user.id"))
    closed_at = Column(Integer)
    created_at = Column(Integer)


class GHIssueLabelsORM(SQLBase):
    __tablename__ = "issue_label"
    id = Column(Integer, primary_key=True)
    issue_id = Column(Integer, ForeignKey("issue.id"))
    label_id = Column(Integer, ForeignKey("label.id"))


class GHIssueAssigneeORM(SQLBase):
    __tablename__ = "issue_assignee"
    id = Column(Integer, primary_key=True)
    user = Column(Integer, ForeignKey("user.id"))


# %%% Implementation entry

def to_stamp(date_time: DateTime) -> int:
    return date_time.replace(tzinfo=timezone.utc).timestamp()

def store_db(c: Connect, s: State):
    for id, val in s.store.issues.pairs():
        if not s.first_processing(val):
            continue
        
        c.session.add(
            GHIssueORM(id=id.value(), name=val.title, user=val.user.value())
        )

        for index, comment in enumerate(val.comments):
            data = s.store.comments.get(comment)
            c.session.add(
                GHCommentORM(
                    id=comment.value(),  #
                    created_at=(to_stamp(data.created_at)),
                    text=data.text,
                    index =index,
                    user=data.user.value()
                )
            )
            

    for id, val in s.store.users.pairs():
        c.session.add(GHUserORM(id=id.value(), name=val.name))

    c.session.commit()


def impl(args):
    if not args.token:
        with open("github-access-token", "r") as f:
            args.token = f.read().replace("\n", "")

    g = gh.Github(args.token)
    repo = g.get_repo("nim-lang/Nim")
    s = State()
    c = Connect()
    s.repo = repo
    s.args = args
    c.engine = sqa.create_engine(f"sqlite:///{args.outfile}")
    Session = sqa.orm.sessionmaker(bind=c.engine)
    c.session = Session()

    SQLBase.metadata.drop_all(c.engine)
    SQLBase.metadata.create_all(c.engine)
    
    
    fill_issues(s)

    store_db(c, s)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        impl(parse_args(["/tmp/Nim-repo.sqlite"]))
    else:
        impl(parse_args())
,