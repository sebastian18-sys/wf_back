const loginRouter = require('express').Router()
const loginController = require('../../controllers/login/loginController')

// LOGIN ROUTER
loginRouter.post('/login', loginController.validate)


module.exports = loginRouter