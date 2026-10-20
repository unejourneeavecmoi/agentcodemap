<?php
namespace App\Models;

use App\Lib\Database;

class UserRepository extends BaseRepo implements RepoInterface {
    private Database $db;

    public function save(array $user): bool {
        return $this->db->insert('users', $user);
    }
}

function bootstrap_repo(): UserRepository {
    return new UserRepository(new Database());
}
