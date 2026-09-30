const groupUsersRouter = require('express').Router()
const userExtractor = require('../../middleware/userExtractor')
const groupUsersController = require('../../controllers/groups/groupUsersController')

// LOGIN ROUTER
// siteRouter.post('/sites/import-identificadores', userExtractor, siteController.importIdentificadores)
groupUsersRouter.get('/sites/get-group-users', userExtractor, groupUsersController.getGroupUsers)
// siteRouter.put("/sites/update-identificadores-by-type", userExtractor, siteController.updateIdentificadoresByType);

module.exports = groupUsersRouter