class Database:
    def __init__(self, dsn):
        self.dsn = dsn
        self.conn = self.connect()

    def connect(self):
        return "conn"

    def insert(self, table, data):
        pass

    def update(self, table, key):
        pass


def slugify(text):
    return text.lower().replace(" ", "-")
