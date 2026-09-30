const groupUsers = require('../../services/groupUsersService');

async function getGroupUsers(req, res) {
    try {
        const data = await groupUsers.getResponsiblesService()
        res.status(200).json({ message: "ok", content: data })
    } catch (error) {
        console.error(`Error while logged groupUsers: ${error}`)
        res.status(500).json({ message: "nok", content: 'Error to insert data' })
    }
}

module.exports = {
    getGroupUsers
}