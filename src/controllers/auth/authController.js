const auth = require('../../services/authServices');


async function getRoles(req, res) {
    try {

        const userId = req.params.id;

        if (!userId) return res.status(400).json({ message: "error", content: { error: 'Missing id' } })

        const [user, roles, permissions] = await Promise.all([
            auth.getUserById(userId),
            auth.getRoleCodesByUserId(userId),
            auth.getPermissionCodesByUserId(userId),
        ]);

        if (!user) return res.status(404).json({ message: "nok", content: "User not found" });

        // const roles = await auth.getRoleCodesByUserId(userId);
        res.status(200).json({ message: "ok", content: {
            user,
            roles,
            permissions
        } })
        
    } catch (error) {
        console.error(`exec error: ${error}`)
        res.status(500).json({ message: "nok", content: { error: error.message } })
    }
}

async function getPermissions(req, res) {
    try {

        // const userId = 4;
        const userId = req.params.id;

        if (!userId) return res.status(400).json({ message: "error", content: { error: 'Missing id' } })

        const permissions = await auth.getPermissionCodesByUserId(userId);
        res.status(200).json({ message: "ok", content: permissions })
    } catch (error) {
        console.error(`exec error: ${error}`)
        res.status(500).json({ message: "nok", content: { error: error.message } })
    }
}



module.exports = {
    getRoles,
    getPermissions
}