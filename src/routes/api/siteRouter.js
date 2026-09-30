const siteRouter = require('express').Router()
const siteController = require('../../controllers/sites/siteController')
const userExtractor = require('../../middleware/userExtractor')

// LOGIN ROUTER
siteRouter.post('/sites/import-identificadores', userExtractor, siteController.importIdentificadores)
siteRouter.get('/sites/get-sites', siteController.getSites)
siteRouter.put("/sites/update-identificadores-by-type", userExtractor, siteController.updateIdentificadoresByType);

module.exports = siteRouter