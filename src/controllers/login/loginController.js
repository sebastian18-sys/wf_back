const login = require('../../services/loginServices');

async function validate(req, res) {
	try {
		const { username, password } = req.body

		if(!username || !password) {
			return res.status(400).json({ok: false, error: 'Missing username or password'})
		}

		const user = await login.validateService(username, password)

		if(!user)  return res.status(401).json({ok: false, error: 'Invalid username or password'})
		res.status(200).json({ message: "ok", content: user })
	
	} catch (error) {
		console.error(`Error while logged users: ${error}`)
		res.status(500).json({ message: "nok", content: 'Error al validar el usuario' })
	}
}

module.exports = {
	validate
}