const users = require('../../services/usersService');

async function getUsers(req, res) {
    try {
        const data = await users.getUsersService()
        res.status(200).json({ message: "ok", content: data })
    } catch (error) {
        console.error(`Error while logged users: ${error}`)
        res.status(500).json({ message: "nok", content: 'Error to insert data' })
    }
}

module.exports = {
    getUsers
}