import yaml
import os

import settings
log = settings.log
from auth_utils import *


#-----client info-----
def handle_validate_client(auth, client_name):
    """
    Checks if the given the client_name value from the config.yaml file matches the name of an existing
    Client in Plextrac. If the client exists in platform, returns the client_id. Otherwise displays a list
    of clients for the user to pick and returns the selected client_id.
    """
    log.info(f'Loading clients...')
    response = request_list_clients(auth.base_url, auth.get_auth_headers())
    if type(response) != list:
        log.critical(f'Could not retrieve clients from instance. Exiting...')
        exit()
    if len(response) < 1:
        log.critical(f'There are no clients in the instance. Exiting...')
        exit()

    if client_name == "":
        if prompt_user_options("client_name was not provided. Do you want to pick an existing client?", "Invalid option", ["y", "n"]) == "y":
            return pick_client(auth, response)
        exit()
    
    clients = list(filter(lambda x: client_name in x['data'], response))

    if len(clients) > 1:
        log.warning(f'client_name value \'{client_name}\' from config matches {len(clients)} Clients in platform. Will need to select one manually...')
        return pick_client(auth, response)

    if len(clients) < 1:
        log.warning(f'Could not find client named \'{client_name}\' in platform. Will need to select one manually...')
        return pick_client(auth, response)

    if len(clients) == 1:
        # example request_list_clients response
        # [
        #   {
        #     "id": "client_1912",
        #     "doc_id": [
        #       1912
        #     ],
        #     "data": [
        #       1912,          // client id
        #       "test client", // cient name
        client_id = clients[0].get('data')[0]
        log.debug(f'found 1 client with matching name in config with client_id {client_id}')
        log.info(f'Found {client_name} client in your PT instance.')
        return client_id, client_name

def pick_client(auth, clients):
    """
    Display the list of clients in the instance to the user and prompts them to picka client.
    Returns the clinet_id of the selected client.
    """
    log.info(f'List of Report Templates in tenant {auth.tenant_id}:')
    for index, client in enumerate(clients):
        log.info(f'Index: {index+1}   Name: {client.get("data")[1]}')

    client_index = prompt_user_list("Please enter a client index from the list above.", "Index out of range.", len(clients))
    client = clients[client_index]
    client_id = client.get('data')[0]
    client_name = client.get("data")[1]
    log.debug(f'returning picked client with client_id {client_id}')
    log.info(f'Selected Client: {client_index+1} - {client_name}')

    return client_id, client_name

#-----end client info-----


#-----report info-----
def handle_get_reports(auth, client_id, client_name):
    """
    Gets a list of reports for a given client.
    Return a list of report names and ids 
    [
        {"id": 500001, "name": "Test Report"}
    ]
    """
    log.info(f'Finding reports for {client_name}...')
    response = request_list_client_reports(auth.base_url, auth.get_auth_headers(), client_id)
    reports = list(map(lambda x: {"id": x['data'][0], "name": x['data'][1]}, response))
    log.debug(reports)

    if len(reports) < 1:
        log.critical(f'Could not find any reports on {client_name}. Exiting...')
        exit()
    log.success(f'Found {len(reports)} reports to export')
    return reports

#-----end client info-----

def sanitize_name_for_file(name):
    # certain characters are not allowed in file names
    invalid_chars = ["\\", "/", ":", "*", "?", "\"", "<", ">", "|"]
    
    new_name = name
    for char in invalid_chars:
        new_name = new_name.replace(char, "")

    return new_name.replace(" ", "_")



if __name__ == '__main__':
    settings.print_script_info()

    with open("config.yaml", 'r') as f:
        args = yaml.safe_load(f)

    auth = Auth(args)
    auth.handle_authentication()

    # get client to import to
    client_name = ""
    if args.get('client_name') != None and args.get('client_name') != "":
        client_name = args.get('client_name')
        log.info(f'Validating client \'{client_name}\' from config...')
    client_id, client_name = handle_validate_client(auth, client_name)

    reports = handle_get_reports(auth, client_id, client_name)
    
    # get files to import
    folder_path = "exported-ptracs"
    try:
        os.mkdir(folder_path)
    except FileExistsError as e:
        log.debug(f'Could not create directory {folder_path}, already exists')

    # export files
    if prompt_user_options(f'Export {len(reports)} reports from {client_name} to PTRAC file(s)', "Invalid option", ["y", "n"]) == "y":
        successful_exports = 0
        for index, report in enumerate(reports):
            log.info(f'({index+1}/{len(reports)}): Exporting \'{report["name"]}\'')
            log.debug(f'exporting report NAME: {report["name"]} ID: {report["id"]}')
            
            # if a report is corrupted and the request does not return the expected JSON data this has the potiential to break the server
            # and fail subsequent request that otherwise would have exported correctly
            #
            # 1 example with a known report in platform that had corrupted data, returned a 502 Bad Gateway
            # then every report after returned the same 502 error. when exporting the reports individually only
            # the corrupted one would fail
            ptrac = request_export_report_to_ptrac(auth.base_url, auth.get_auth_headers(), client_id, report['id'])
            
            log.debug(f'type of returned object from server is {type(ptrac)}')
            if type(ptrac) != dict:
                log.error(f'File response from server was invalid. Skipping...')
                log.debug(ptrac.text)
                continue

            file_name = f'{sanitize_name_for_file(client_name)}_{sanitize_name_for_file(report["name"])}_{time.strftime("%Y_%m_%d_%H_%M_%S", time.localtime(time.time()))}.ptrac'
            file_path = f'{folder_path}/{file_name}'
            with open(f'{file_path}', 'w') as file:
                json.dump(ptrac, file)
                log.success(f'Saved \'{report["name"]}\' report to \'{file_name}\'')
                successful_exports +=1
        
        log.success(f'Successfully exported {successful_exports}/{len(reports)} report(s). File(s) can be found in {folder_path}')
