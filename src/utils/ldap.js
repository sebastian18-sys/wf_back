const {Client} = require('ldapts')

module.exports = async function ldap(user, pass) {
    if (user && pass) {

        if (!user || !pass) return { auth: false };

        // If process development return static user data
        if(process.env.NODE_ENV === 'development') {
            return {
                auth: false, 
                auth_provider: "LDAP",
                username: user,
                ldap_dn: null,
                firstName: 'User', 
                lastName: 'Test', 
                email: 'user.test@entel.pe', 
                title: 'INTERNO', 
                company: 'ENTEL PERU', 
                companyShort: 'ENTEL PERU', 
                department: 'ENTEL PERU', 
                mailNickname: 'user.test', 
                office: 'PERU'
            }
        }

        // config
        const dominio = 'nextelperu.net'
        const ip = '14.240.4.146'
        const url = `ldap://${ip}:389`
        const adSuffix = `dc=nextelperu,dc=net`

        const client = new Client({url})

        let isAuthenticate
        let data = {}
        try {
            await client.bind(`${user}@${dominio}`, pass)
            isAuthenticate = true
            // search data
            const { searchEntries } = await client.search(adSuffix, {scope: 'sub', filter: `(samaccountname=${user})`})
            const {sn, givenName, title, physicalDeliveryOfficeName, department, company, mailNickname, mail} = searchEntries[0]
            data = {
                auth_provider: "LDAP", //new
                username: user, //new
                ldap_dn: null, //new
                firstName: givenName,
                lastName: sn,
                email: mail,
                title: title ? title : 'EXTERNO',
                company: company ? company : 'ENTEL EXTERNO',
                companyShort: company ? company : 'ENTEL EXTERNO',
                department: department ? department : 'ENTEL EXTERNO',
                mailNickname,
                office: physicalDeliveryOfficeName
            }

            console.log(data)
        } catch (e) {
            console.log(e)
            isAuthenticate = false
        } finally {
            await client.unbind()
        }
        return isAuthenticate ? {auth: true, ...data} : {auth: false}
    }
}
