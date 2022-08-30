#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Aug 30 14:28:42 2022

@author: haxscramper
"""

import sqlalchemy as sqa

import argparse
import github as gh
import sqlite3
import sys
from typing import List, Type, Generic, TypeVar, Dict
from sqlalchemy.orm import declarative_base

SQLBase = declarative_base()

Val = TypeVar("T")
Id = TypeVar("Id", bound="DODId")


class DODId(Generic[Id, Val]):
    __value__: int

    def __init__(self, value: int):
        self.__value__ = value


class DODStore(Generic[Id, Val]):
    store: List[Val]
    __IdType__: Type[Id]
    __ValType__: Type[Val]

    def __init__(self, ValType: Type[Val], IdType: Type[Id]):
        pass

    def add(self, value: Val) -> Id:
        result = len(self.store)
        self.store.append(value)
        return self.__ValType__(result)

    def get(self, id: Id) -> Val:
        return self.store[id]


class DODInternStore(Generic[Id, Val]):
    __map__: Dict[Val, Id]
    __store__: DODStore[Id, Val]

    def add(self, value: Val) -> Id:
        if value not in self.__map__:
            self.__map__[value] = self.__store__.add(value)

        return self.__map__[value]

    def get(self, id: Id) -> Val:
        return self.__store__.get(id)


class GHUser:
    name: str


class GHUserId(DODId):
    pass


class GHStar:
    user: GHUserId


class GHStarId(DODId):
    pass


class GHStore:
    users: DODInternStore[GHUserId, GHUser]

    def add_user(self, user: GHUser) -> GHUserId:
        return self.users.add(user)


class GHStarORM(SQLBase):
    __tablename__ = "stars"

    id = sqa.Column(sqa.Integer, primary_key=True)
    user = sqa.Column(sqa.Integer)

    def __repr__(self):
        return f"GHStarORM(id={self.id!r}, user={self.user!r})"


class GHUserORM(SQLBase):
    __tablename__ = "users"

    id = sqa.Column(sqa.Integer, primary_key=True)
    name = sqa.Column(sqa.Text())

    def __repr__(self):
        return f"GHUserORM(id={self.id!r}, name={self.name!r})"


class State:
    engine: sqa.engine.Engine
    con: sqlite3.Connection
    args: argparse.Namespace
    repo: gh.Repository
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


def fill_stargazers(s: State):
    for star in s.repo.get_stargazers_with_dates():
        print(f"{star.user} at {star.starred_at}")


def fill_issues(s: State):
    pass


def impl(args):
    if not args.token:
        with open("github-access-token", "r") as f:
            args.token = f.read().replace("\n", "")

    g = gh.Github(args.token)
    repo = g.get_repo("nim-lang/Nim")
    s = State()
    s.repo = repo
    s.args = args
    s.con = sqlite3.connect(args.outfile)
    s.engine = sqa.create_engine(f"sqlite:///{args.outfile}")
    Session = sqa.orm.sessionmaker(bind=s.engine)
    s.session = Session()
    # fill_stargazers(s)

    SQLBase.metadata.create_all(s.engine)
    s.session.add(GHUserORM(name="name"))


if __name__ == "__main__":
    if len(sys.argv) == 1:
        impl(parse_args(["/tmp/Nim-repo.sqlite"]))
    else:
        impl(parse_args())
