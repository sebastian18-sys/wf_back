const jwt = require('jsonwebtoken')
const dotenv = require('dotenv')
dotenv.config()

const userExtractor = (req, res, next) => {

	const authorization = req.get('authorization')
	
	let token = ''
	if(authorization && authorization.toLowerCase().startsWith('bearer')) {
		token = authorization.substring(7)
	}
    
    if (!token) {
        return res.status(401).json({ error: "token missing" });
    }

	let decodedToken = {}

	decodedToken = jwt.verify(token, process.env.SECRET)

	if(!token || !decodedToken.user_id) {
		return res.status(401).send({ error: 'token invalid' })
	}

    console.log("DECODED TOKEN FINAL", decodedToken)

	const { user_id: userId } = decodedToken
	req.userId = userId
	next()
}

module.exports = userExtractor