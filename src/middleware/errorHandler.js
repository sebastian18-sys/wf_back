const dotenv = require('dotenv')
dotenv.config()

const ERROR_HANDLER = {
	'CastError': res => res.status(400).send({ error: 'id used is malformed'}),
	'ValidateError': (res, error) => res.status(409).send({ error: error.message }),
	'JsonWebTokenError': res => res.status(401).send({ error: 'token missing or invalid' }),
	'TokenExpirerError': res => res.status(401).send({ error: 'token expired' }),
	'BadRequest': res => res.status(400).send({ error: 'Bad Request' }),
	defaultError: res => res.status(500).end() 
}

const errorHandler=(err, req, res)=>{
	const handler = ERROR_HANDLER[err.name] || ERROR_HANDLER.defaultError
	handler(res, err)
	// const statusCode = res.statusCode === 200 ? 500:res.statusCode
	// res.status(statusCode)
	// res.json({
	// 	message:err.message,
	// 	stack:process.env.NODE_ENV === 'production' ? null : err.stack,
	// })
}

module.exports = errorHandler