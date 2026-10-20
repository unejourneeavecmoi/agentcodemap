from lib.db import Database
from lib.utils import slugify


class User:
    def __init__(self, db):
        self.db = db

    def save(self):
        self.db.insert("users", {"name": self.name})


class Admin(User):
    def promote(self, user):
        slug = slugify(user.name)
        self.db.update("users", slug)
        return slug


def main():
    db = Database("sqlite:///app.db")
    admin = Admin(db)
    admin.promote(User(db))
