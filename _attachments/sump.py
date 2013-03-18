#!/usr/bin/env python
import os,subprocess
import pika,couchdbkit,json
import yaml,adapter,traceback,time
base_ttl = 2
proc = yaml.load(open('process.yaml').read())
current_set =  {}

def callback(ch, method, properties, body):
	try:
		ref = json.loads(body)
		if type(ref) != type({}):
			ch.basic_ack(delivery_tag = method.delivery_tag)
			ch.basic_publish('error','error',json.dumps({'error':body}))
			print body+' not dict'	
			return
	except:
		print body+' not json'
		ch.basic_ack(delivery_tag = method.delivery_tag)
		ch.basic_publish('error','error',json.dumps({'error':body}))
		return
	print method.exchange,method.routing_key,ref
	exchange = method.exchange
	routing_key = method.routing_key
	if 'ttl' in ref:
		ref['ttl'] = ref['ttl'] - 1
		if ref['ttl'] == 0:
			ch.basic_ack(delivery_tag = method.delivery_tag)
			return
	else:
		ref['ttl'] = base_ttl
	
	if exchange in proc:
		print '==> '+exchange
		if routing_key in proc[exchange]:
			print '===> '+routing_key
			target_spool = proc[exchange][routing_key]
			if cq.redis.exists('recent:'+routing_key):
				cq.message(json.dumps(ref),routing_key,exchange)
			else:
				print 'binding '+exchange+'->'+target_spool
				ch.queue_declare(queue=target_spool,arguments={'x-expires':30000})
				ch.queue_bind(queue=target_spool,exchange=exchange,routing_key=routing_key)
				print 'resending '+str(ref)+' to '+exchange+'=>'+routing_key
				cq.message(json.dumps(ref),routing_key,exchange)
				print 'sending start to '+routing_key
				ch.basic_publish('command','spindle',json.dumps({'bobbin':target_spool}))
				cq.redis.set('recent:'+routing_key,'')
				cq.redis.expire('recent:'+routing_key,30)
				print current_set
		else:
			print 'unknown key '+routing_key
			ch.basic_publish('error','error',json.dumps({'error':ref}))
	ch.basic_ack(delivery_tag = method.delivery_tag)

def gen_exchanges():
	print 'building sump'
	cq.channel.exchange_declare(exchange='sump',exchange_type='topic',arguments={'alternate-exchange':'fail'}) 
	cq.channel.queue_declare(queue='sump_spool')
	cq.channel.queue_bind(queue='sump_spool',exchange='sump',routing_key='*')
	print 'building error'
	#cq.channel.exchange_declare(exchange='error',exchange_type='fanout',arguments={}) 
	#cq.channel.queue_declare(queue='error_spool')
	#cq.channel.queue_bind(queue='error_spool',exchange='error',routing_key='*')
	print 'building top level exchanges'
	for i in proc.keys():
		print 'primary exchange '+i
		cq.channel.exchange_declare(exchange=i,exchange_type='topic',arguments={'alternate-exchange':'sump'}) 
	
if __name__ == "__main__":
	cq = adapter.couch_queue()
	gen_exchanges()
	cq.channel.basic_publish('command','start',json.dumps({'base':'start'}))
	cq.channel.basic_publish('error','error',json.dumps({'base':'start'}))
	cq.run_queue('sump_spool',callback)
