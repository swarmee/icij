#!/bin/bash

# Wait for Elasticsearch to start up before doing anything.
until curl -s http://elasticsearch:9200/_cat/health -o /dev/null; do
    echo Waiting for Elasticsearch...
    sleep 10
done


# Wait for Kibana to start up before doing anything.
until curl -s http://kibana:5601/login -o /dev/null; do
    echo Waiting for Kibana...
    sleep 10
done


# load ingest_pipeline
echo 'Loading pipeline'
curl -s -H 'Content-Type: application/json' -XPUT 'http://elasticsearch:9200/_ingest/pipeline/parse_products?pretty' -d @/tmp/sample/parse-products-pipeline.json

# load index Template
echo 'Load Index Template'
curl -s -H 'Content-Type: application/json' -XPUT 'http://elasticsearch:9200/_template/products-v2?pretty' -d @/tmp/sample/products-index-template.json


# Delete Old index 
curl -s -X DELETE "http://elasticsearch:9200/products-v2?pretty" -H "Content-Type: application/json"

# load data
echo 'Load Data'

while read f1
do        
   curl -s -XPOST 'http://elasticsearch:9200/products-v2/_doc?pipeline=parse_products' -H "Content-Type: application/json" -d "{ \"input\": \"$f1\" }"
done < /tmp/sample/competitor-products.csv

echo 'Templates and Data all loaded up - shutting down container'


