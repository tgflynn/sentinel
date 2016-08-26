#!/usr/bin/env python

import argparse
import sys
import os
sys.path.append("lib")
sys.path.append("scripts") 

dir_path = os.path.dirname(os.path.realpath(__file__))

sys.path.append( os.path.abspath( os.path.join( dir_path, ".." ) ) )

import cmd
import misc
import libmysql
import config
import crontab
import cmd, sys
import govtypes
import random 
import json 
import time
import datetime

from sentineld import GovernanceObject, Proposal, Superblock, Event, GFACTORY
#from governance import GovernanceObject, GovernanceObjectMananger, Setting, Event
#from classes import Proposal, Superblock
from dashd import CTransaction, rpc_command

PAYMENT_ADDRESS1 = "yNaE8Le2MVwk1zpwuEKveTMCEQHVxdcfCS"
PAYMENT_AMOUNT1 = "0.127"

PAYMENT_ADDRESS2 = "yPY6JNMQXdhxqP41yK6rL9ZNbZhDGyfmTB"
PAYMENT_AMOUNT2 = "23"

DESCRIPTION_URL = "'www.dashwhale.org/p/sb-test'"

START_DATE = "2016-08-01"
END_DATE = "2017-01-01"

print "config.username = ", config.username

db = libmysql.connect(config.hostname, config.username, config.password, config.database)

response = rpc_command( "getblockcount" )
print "response = ", response

blockCount = int( response )

print "block count = ", blockCount

def get_block_count():
    blockCount = int(rpc_command("getblockcount"))
    return blockCount

def wait_for_blocks(n,initial=None):
    if initial is None:
        initial = get_block_count()
    while (get_block_count() - initial) < n:
        time.sleep(30)

def vote(hash):
    command = "gobject vote-conf %s funding yes" % ( hash )
    print "vote: command = ", command
    rpc_command(command)

def do_test():
    start_epoch = datetime.datetime.strptime(START_DATE, "%Y-%m-%d").strftime('%s')
    end_epoch = datetime.datetime.strptime(END_DATE, "%Y-%m-%d").strftime('%s')
    
    # Step 1 - Create proposal

    proposal_name = "tprop-" + str(random.randint(1000000, 9999999))

    fee_tx = CTransaction()

    newObj = GFACTORY.create( 'proposal', proposal_name )
    newObj.object_revision = govtypes.FIRST_REVISION
    newObj.description_url = DESCRIPTION_URL
    newObj.start_epoch = start_epoch
    newObj.end_epoch = end_epoch
    newObj.payment_address = PAYMENT_ADDRESS2
    newObj.payment_amount = PAYMENT_AMOUNT2
    newObj.updateObjectData()
    last_id = newObj.store()

    if last_id is None:
        raise(Exception("do_test: proposal creation failed"))

    # CREATE EVENT TO TALK TO DASHD / PREPARE / SUBMIT OBJECT
                
    event = Event( last_id )
    event.start_time = misc.get_epoch()
    event.store()


do_test()
        

