import { Router } from 'express';
import { Database } from '../lib/db';

export class UserRouter {
  constructor(db: Database) {
    this.db = db;
  }

  handle(req, res) {
    this.db.insert('users', req.body);
  }
}

export async function bootstrap() {
  const router = new UserRouter(new Database('sqlite:///app.db'));
  router.handle({}, {});
}
