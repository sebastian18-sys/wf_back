const db = require("../db/conn");

async function getUserById(id) {
    try {
        const userData = await db.query(
            `
                SELECT user_id, username, email, first_name, last_name
                FROM users
                WHERE user_id = ? LIMIT 1
            `, [id]
        )
        return userData
    } catch (error) {
        console.error(`exec error: ${error}`);
        return { error: error.message }
    }
}

async function getRoleCodesByUserId(id) {
    try {
        const userData = await db.query(
            `
                SELECT DISTINCT r.code
                FROM roles r
                JOIN user_roles ur ON ur.role_id = r.role_id
                WHERE ur.user_id = ?
            `, [id]
        )
        return userData
    } catch (error) {
        console.error(`exec error: ${error}`);
        return { error: error.message }
    }
}

async function getPermissionCodesByUserId(id) {

    try {
        const userData = await db.query(
            `
                SELECT DISTINCT p.code
                FROM permissions p
                JOIN role_permissions rp ON rp.permission_id = p.permission_id
                JOIN user_roles ur ON ur.role_id = rp.role_id
                WHERE ur.user_id = ?
            `, [id]
        )

        return userData
    } catch (error) {
        console.error(`exec error: ${error}`);
        return { error: error.message }
    }
}



module.exports = {
    getUserById,
    getRoleCodesByUserId,
    getPermissionCodesByUserId
}