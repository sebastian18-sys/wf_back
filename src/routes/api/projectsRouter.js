const projectsRouter = require('express').Router()
const projectsController = require('../../controllers/projects/projectsController')
const userExtractor = require('../../middleware/userExtractor')

// LOGIN ROUTER
projectsRouter.get('/projects/get-project', userExtractor, projectsController.getProjects)
projectsRouter.get('/projects/get-project/info/:id', projectsController.getProjectsInfoById)
// projectsRouter.post('/projects/create', userExtractor, projectsController.uploadDataCapex)

module.exports = projectsRouter