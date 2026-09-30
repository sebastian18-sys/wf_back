const authRouter = require('express').Router()
const authController = require('../../controllers/auth/authController')

// LOGIN ROUTER
authRouter.get('/auth/permissions/:id', authController.getPermissions)
authRouter.get('/auth/me/:id', authController.getRoles)


module.exports = authRouter