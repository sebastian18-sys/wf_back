const db = require("../db/conn");

async function getUsersService() {
    try {
        const usersData = await db.query(`
            SELECT 
                *
            FROM users
        `)
        return usersData
    } catch (error) {
        console.error(`exec error: ${error}`);
        return { error: error.message }
    }
}

module.exports = {
    getUsersService
};