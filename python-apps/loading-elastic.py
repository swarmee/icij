from elasticsearch import helpers, Elasticsearch
import csv

filename = './data.csv'
es = Elasticsearch('test.swarmee.net', port=9200)
indexName = "my-index"
indexType = "my-type"
actionsPerBulk=5000
es.indices.delete(index=indexName, ignore=[400, 404])
indexSettings = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 1
    },
    "mappings": {
        "my-type": {
            "properties": {
            }
        }
    }
}
es.indices.create(index=indexName, body=indexSettings)

actions = []

fields = []
with zipfile.ZipFile(filename) as z:
    for zippedFilename in z.namelist():
        numLines = 0
        data = StringIO.StringIO(z.read(zippedFilename))
        reader = csv.reader(data)
        for row in reader:
            numLines += 1
            if numLines == 1:
                fields = row
            else:
                doc = {
                	'reviewerId': row[0],
                 	'vendorId': row[1],
                 	'rating':int(row[2]),
                 	'date':row[3]
                }
                action = {
                        "_index": indexName,
                        '_op_type': 'index',
                        "_type": "review",
                        "_source": doc
                }
                actions.append(action)
                # Flush bulk indexing action if necessary
                if len(actions) >= actionsPerBulk:
                    try:
                        helpers.bulk(es, actions)
                    except:
                        print ("Unexpected error:", sys.exc_info()[0])
                    del actions[0:len(actions)]
                    print (numLines)

if len(actions) > 0:
    helpers.bulk(es, actions)


with open(filename) as f:
    reader = csv.DictReader(f)
    helpers.bulk(es, reader, index='my-index', doc_type='my-type')


_____________________________________________________________________________________

from elasticsearch import helpers
from elasticsearch.client import Elasticsearch
import time
import argparse
import json

#   This is a generic script to scroll information from one event-centric index sorted 
#   by entity ID (e.g. a person) and bundle related events in update calls to an entity
#   centric index which summarises behaviours over time 

parser = argparse.ArgumentParser()
parser.add_argument("eventIndexName", help="The name of the index which will receive events")
parser.add_argument("eventDocType", help="Name of the event type")
parser.add_argument("eventQueryFile", help="The JSON file with the query for events")
parser.add_argument("entityIdField", help="The name of the field with the entity ID")
parser.add_argument("entityIndexName", help="The name of the index which will build entities")
parser.add_argument("entityDocType", help="Name of the entity type")
parser.add_argument("updateScriptFile", help="The script file used to update entities with events")

parser.add_argument("-actionsPerBulk", help="The number of records to send in each bulk request", type=int, default=5000)
parser.add_argument("-eventsPerScrollPage", help="The number of events per scroll page (small=slow)",  type=int, default=5000)
parser.add_argument("-maxTimeToProcessScrollPage", help="The max time to process page of events",  default="1m")
parser.add_argument("-scriptMode", help="The mode parameter passed to the script", default="fullBuild")
args = parser.parse_args()

eventsQuery = json.load(open(args.eventQueryFile))
es = Elasticsearch('test.swarmee.net', port=9200)

def generate_actions():
    def get_action(events):
        return {
            '_op_type': 'update',
            "_id": lastEntityId,
            "scripted_upsert":True,
            # In elasticsearch >=2.0
            #"script": {
            #    "file": args.updateScriptFile,
            #            "params": {
            #                "scriptMode": args.scriptMode,
            #                "events":list(events)
            #            }
            #},
            # In elasticsearch <2.0
            "script": args.updateScriptFile,
            "params": {
                "scriptMode": args.scriptMode,
                "events":list(events)
            },
            
            "upsert" : {
            # Use a blank document because script does all the initialization
            }
        }

    lastEntityId = ""
    events = []
    numDocsProcessed = 0
    start = time.time()
    for doc in helpers.scan(es,
            index=args.eventIndexName,
            doc_type=args.eventDocType,
            query=eventsQuery,
            size=args.eventsPerScrollPage,
            scroll=args.maxTimeToProcessScrollPage,
            preserve_order=True):

        thisEntityId = doc["_source"][args.entityIdField]

        # end of event group
        if thisEntityId != lastEntityId:
            if events:
                yield get_action(events)
            events = []
            lastEntityId = thisEntityId
        events.append(doc["_source"])
        numDocsProcessed += 1
        if numDocsProcessed % 10000 == 0:
            elapsedSecs = int(time.time() - start)
            dps =  numDocsProcessed/max(1,elapsedSecs)
            print numDocsProcessed, "docs per second=",dps

    # load last event group too
    if events:
        yield get_action(events)

    print "Processed", numDocsProcessed, "docs"

start = time.time()
helpers.bulk(es, generate_actions(),
    index=args.entityIndexName,
    doc_type=args.entityDocType,
    chunk_size=args.actionsPerBulk)

elapsed = (time.time() - start)
print "elapsed time=",elapsed
__________________________________________________________


//====================================
//===    Reviewer-centric object =====
//====================================
// This script summarises the reviews
// made by a single marketplace reviewer.
// A history of the last 50 reviews is kept
// and a profile is determined:
// "newbie" - less than 5 reviews
// "regular" - more than 5 reviews
// "fanboy" - > 5 reviews, all positive, 
//            always for the same vendor
// "hater" - > 5 reviews, all negative, 
//            always for the same vendor
// "unlucky" - > 5 reviews, mainly negative, 
//            across multiple vendors
//====================================

int MAX_RECENT_REVIEWS_HELD = 50;


// Extract the doc source to a field
doc = ctx._source;

// If this is an "upsert" where we 
// need to initialize a new doc...
if("create".equals(ctx.op)){
    //initialize entity state
    doc.recentReviews = [];
    doc.profile = "newbie";
    doc.rating5Count = 0;
    doc.rating4Count = 0;
    doc.rating3Count = 0;
    doc.rating2Count = 0;
    doc.rating1Count = 0;
    doc.totalNumReviews = 0;
    doc.vendorSummaries = [];
}


// Convert basic array into map for ease of manipulation (could 
// use a priority queue here)
vendorMap = doc.vendorSummaries.collectEntries{[it.vendorId, it]};

// Append the new events into history, update per-vendor summaries
for (review in events){
    doc.recentReviews.add(review);
    //Add a truncated form of date string for coincidence checks
    //review.timeCoincidenceKey = review.date[0..review.date.size()-2]
    doc.totalNumReviews++;

    vendorSummary = vendorMap.get(review.vendorId);
    if(vendorSummary == null){
        //First time-review for a vendor - initialize ratings structure
        vendorSummary = [
                        "vendorId":review.vendorId,
                        "reviewTotals":[0,0,0,0,0,0]
                        ];
        vendorMap.put(review.vendorId, vendorSummary);
    }
    //Add one to the number of reviews with this rating
    vendorSummary.reviewTotals[review.rating]++;

    //Add one to the total number of reviews given with this star rating
    ratingCounterName = "rating" + review.rating + "Count";
    doc.put(ratingCounterName,doc.get(ratingCounterName)+1);
}
//Store the vendor map back as an array
doc.vendorSummaries = vendorMap.values();

doc.numVendors = vendorMap.size();
doc.positivity = (int)(((doc.rating4Count+doc.rating5Count) / doc.totalNumReviews) *100);
doc.negativity = (int)(((doc.rating2Count+doc.rating1Count) / doc.totalNumReviews) *100);

doc.profile = "newbie";
if(doc.totalNumReviews > 5){
    doc.profile="regular";
    if(doc.positivity > 50){
        if(doc.numVendors == 1){
            doc.profile="fanboy"
        }
    }else{
        if(doc.numVendors == 1){
            doc.profile="hater"
        } else {
            doc.profile="unlucky"
        }
    }
}
if(scriptMode == "fullBuild"){
	// The review content being received is the totality of all content we expect to
	// gather for this entity. We can therefore to decide if the sum total of this
	// user's activity is interesting and if not we can avoid indexing the contents.
	if ((doc.profile == "newbie")||(doc.profile == "regular")) {
		// We choose to abort the insert for "boring" profiles.
		ctx.op ="none"; 
	}
}
//Trim the history of recent reviews to avoid excessive growth over time
int numRecentReviews = doc.recentReviews.size();
if(numRecentReviews > MAX_RECENT_REVIEWS_HELD){
    doc.recentReviews = doc.recentReviews[(numRecentReviews-MAX_RECENT_REVIEWS_HELD)..-1];
}
