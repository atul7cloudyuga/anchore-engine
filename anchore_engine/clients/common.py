import re
import copy
import json
import time
import random

import anchore_engine.configuration.localconfig
from anchore_engine import db
from anchore_engine.db import db_services
from anchore_engine.subsys import logger

localconfig = None

scache = {}
scache_template = {'records': [], 'ttl': 15, 'last_updated': 0}

def update_service_cache(user_auth, servicename, skipcache=False):
    global scache, scache_template

    fromCache = True
    if skipcache or servicename not in scache:
        scache[servicename] = copy.deepcopy(scache_template)        
        fromCache = False

    if not scache[servicename]['records']:
        fromCache = False
    else:
        for record in scache[servicename]['records']:
            if not record['status']:
                fromCache = False

    if (time.time() - scache[servicename]['last_updated']) > scache[servicename]['ttl']:
        fromCache =  False

    if not fromCache:
        # refresh the cache for this service from catalog call
        try:
            logger.debug("fetching services ("+str(servicename)+")")
            with db.session_scope() as dbsession:
                service_records = db.db_services.get_byname(servicename, session=dbsession)
            #service_records = get_service(user_auth, servicename=servicename)
            logger.debug("services fetched: " + str(service_records))
        except Exception as err:
            logger.warn("cannot get service: " + str(err))
            service_records = []

        scache[servicename]['records'] = []
        if service_records:
            for service_record in service_records:
                if service_record['status']:
                    scache[servicename]['records'].append(service_record)
                    scache[servicename]['last_updated'] = time.time()

    return(fromCache)
    
def get_enabled_services(user_auth, servicename, skipcache=False):
    global scache, scache_template

    fromCache = update_service_cache(user_auth, servicename, skipcache=skipcache)

    # select a random enabled, available service
    if scache[servicename]['records']:
        ret = list(scache[servicename]['records'])
        random.shuffle(ret)
    else:
        ret = []

    if not ret:
        logger.debug("no services of type ("+str(servicename)+") are yet available in the system")
       
    return(ret)
    
def choose_service(user_auth, servicename, skipcache=False):
    global scache, scache_template

    fromCache = update_service_cache(user_auth, servicename, skipcache=skipcache)

    # select a random enabled, available service
    if scache[servicename]['records']:
        idx = random.randint(0, len(scache[servicename]['records'])-1)
        ret = scache[servicename]['records'][idx]
    else:
        ret = {}

    if not ret:
        logger.debug("no service of type ("+str(servicename)+") is yet available in the system")
        
    return(ret)
    
def get_service_endpoint(user_auth, servicename, api_post=None):
    global localconfig

    if localconfig == None:
        localconfig = anchore_engine.configuration.localconfig.get_config()

    base_url = None

    # look for override, else go to the DB
    if servicename+'_endpoint' in localconfig:
        base_url = re.sub("/+$", "", localconfig[servicename+'_endpoint'])
        if api_post:
            base_url = '/'.join([base_url, api_post])
        return(base_url)

    try:
        service_record = choose_service(user_auth, servicename)
        if not service_record:
            raise Exception("cannot locate registered and available service in config/DB: " + servicename)
        else:
            endpoint = service_record['base_url']
            if endpoint:
                apiversion = service_record['version']
                base_url = '/'.join([endpoint, apiversion])
                if api_post:
                    base_url = '/'.join([base_url, api_post])
            else:
                raise Exception("cannot load valid endpoint from service record: " + servicename)

    except Exception as err:
        raise Exception("could not find valid endpoint for service ("+servicename+") - exception: " + str(err))
    
    logger.debug("got endpoint ("+servicename+"): " + str(base_url))
    return(base_url)

def get_service_endpoints(user_auth, servicename, api_post=None):
    global localconfig

    if localconfig == None:
        localconfig = anchore_engine.configuration.localconfig.get_config()

    base_url = None
    base_urls = []

    # look for override, else go to the DB
    if servicename+'_endpoint' in localconfig:
        base_url = re.sub("/+$", "", localconfig[servicename+'_endpoint'])
        if api_post:
            base_url = '/'.join([base_url, api_post])
        base_urls = [base_url]
        return(base_urls)

    try:
        service_records = get_enabled_services(user_auth, servicename)
        if not service_records:
            raise Exception("cannot locate registered and available service in config/DB: " + servicename)
        else:
            for service_record in service_records:
                endpoint = service_record['base_url']
                if endpoint:
                    apiversion = service_record['version']
                    base_url = '/'.join([endpoint, apiversion])
                    if api_post:
                        base_url = '/'.join([base_url, api_post])
                    if base_url not in base_urls:
                        base_urls.append(base_url)
            
            if not base_urls:
                raise Exception("cannot load valid endpoint from service record: " + servicename)

    except Exception as err:
        raise Exception("could not find valid endpoint for service ("+servicename+") - exception: " + str(err))
    
    logger.debug("got endpoints ("+servicename+"): " + str([base_urls]))
    return(base_urls)