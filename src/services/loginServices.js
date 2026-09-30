const bcrypt = require('bcrypt')
const jwt = require('jsonwebtoken')
const { verifyTurnstile } = require('../middleware/verify-turnstile');
const dotenv = require('dotenv')
const ldap = require('../utils/ldap')
const db = require("../db/conn");
dotenv.config() 


async function upsertInternalUserAndRole(ldap) {

    try {
        
        const existUser = await db.query(`SELECT * FROM users WHERE username = ?`, [ldap.username])
        let userId;

        if(!existUser || existUser.length == 0) {
            // Create INTERNAL USER

            const ins = await db.query(`
                INSERT INTO users (auth_provider, username, ldap_dn, first_name, last_name, email, job_title, company, phone, password_hash, is_active, created_at)
                VALUES ('LDAP', ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 1, NOW())`, 
                [
                    ldap.username,
                    ldap.ldap_dn ?? null,
                    ldap.firstName ?? null,
                    ldap.lastName ?? null,
                    ldap.email ?? null,
                    ldap.title ?? null,
                    ldap.company ?? null,
                ]
            )

            userId = ins.insertId

        } else {

            userId = existUser[0].user_id

            // 3) actualizar datos cada login (no tocas password)
            await db.query(`
                UPDATE users
                SET ldap_dn = ?, first_name = ?, last_name = ?, email = ?, job_title = ?, company = ?
                WHERE user_id = ?
            `, [
                ldap.ldap_dn ?? null,
                ldap.firstName ?? null,
                ldap.lastName ?? null,
                ldap.email ?? null,
                ldap.title ?? null,
                ldap.company ?? null,
                userId,
            ])
        }

        // 4) asignar rol por defecto INTERNAL_USER si no lo tiene
        const roles = await db.query(`SELECT role_id FROM roles WHERE code = 'INTERNAL_USER'`)
        
        if(!roles || roles.length == 0) throw new Error('INTERNAL_USER role not found')

        const roleId = roles[0].role_id

        await db.query(`
            INSERT IGNORE INTO user_roles (user_id, role_id)
            VALUES (?, ?)
        `, [userId, roleId])

        return userId

    } catch (error) {
        console.error(`exec error: ${error}`);
        return { error: error.message }
    }
}

async function validateService(username, password) {
	
    try {

        const result = await ldap(username, password);

        // NOT FOUND
        if(!result) {
            throw new Error('Invalid username or password')
        }

        // EXTERNAL USER
        if(!result.auth) {

            const user = await db.query(`SELECT * FROM users WHERE username = ?`, [username])
            
            if(!user || user.length == 0) {
                throw new Error('Invalid username or password')
            }
            
            const data = user
            const passwordDB = data[0].password_hash

            const passwordCorrect = data[0].username == null
                ? false
                : await bcrypt.compare(password, passwordDB)

            if(!(user && passwordCorrect)) throw new Error('Invalid username or password')

            const userToken = data[0]

            //Signed
            const token = jwt.sign(userToken, process.env.SECRET)
            console.log(data[0])

            return {
                auth: true,
                id: data[0].user_id,
                firstName: data[0].first_name,
                lastName: data[0].last_name,
                email: data[0].email, 
                title: data[0].job_title, 
                company: data[0].company, 
                companyShort: 'EXTERNO', 
                department: 'EXTERNO', 
                mailNickname: data[0].email.split('@')[0],
                office: 'PERU',
                token
            }

        }

        // INTERNAL USER
        if(result.auth) {

            const userId = await upsertInternalUserAndRole(result)

            const payload = {
                user_id: userId,
                firstName: result.firstName,
                lastName: result.lastName,
                email: result.email, 
                title: result.title, 
                company: result.company, 
                companyShort: result.companyShort, 
                department: result.department, 
                mailNickname: result.mailNickname, 
                office: result.office
            }

            const token = jwt.sign(payload, process.env.SECRET)
            console.log(userId)

            return {
                auth: true,
                id: userId,
                firstName: result.firstName,
                lastName: result.lastName,
                email: result.email, 
                title: result.title, 
                company: result.company, 
                companyShort: result.companyShort, 
                department: result.department, 
                mailNickname: result.mailNickname,
                office: result.office,
                token
            }

        }
        
    } catch (error) {

        console.error(`exec error: ${error}`);
        // res.send({"message": "NOK", "content": error});
    }

}

module.exports = {
	validateService
}