const usersRouter = require('express').Router()
const usersController = require('../../controllers/users/usersController')
const userExtractor = require('../../middleware/userExtractor')

// LOGIN ROUTER
// siteRouter.post('/sites/import-identificadores', userExtractor, siteController.importIdentificadores)
usersRouter.get('/sites/get-users', userExtractor, usersController.getUsers)
// siteRouter.put("/sites/update-identificadores-by-type", userExtractor, siteController.updateIdentificadoresByType);

module.exports = usersRouter