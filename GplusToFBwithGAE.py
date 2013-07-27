#!/usr/bin/env python
import webapp2
import urllib2, urllib
import json
from datetime import datetime
from HTMLParser import HTMLParser
from htmlentitydefs import name2codepoint
from google.appengine.ext import db

apiKey = 'API_Keys_obtained_in_step_2'
FB_appID, FB_appSecret = '467522106672018', '6bf332e3e8d2bc781d80e88ee549d890' # I highly recommend replacing these 2 with your own FB app's data
fbUserID = 'FB_id_obtained_in_step6_(2)_goes_here' # obtained by "http://graph.facebook.com/FB_username"
gplusUserID = 'GPlus_profile_id_obtained_in_step7'

class LatestPost(db.Model):
    postDatetime = db.DateTimeProperty()

class MLStripper(HTMLParser):
    def __init__(self):
        self.reset()
        self.fed = []
    def handle_entityref(self, name):
        self.fed.append(unichr(name2codepoint[name]))
    def handle_charref(self, name):
        self.fed.append(unichr(int(name)))
    def handle_data(self, d):
        self.fed.append(d)
    def get_data(self):
        return ''.join(self.fed)

def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()

class FetchAndRepost(webapp2.RequestHandler):

    def get(self):
        # check whether an entity already exists
        keyName = 'public_GAEtoFB_{0}'.format(gplusUserID)
        latestPost = db.get(db.Key.from_path('LatestPost', keyName))
        if latestPost is None:
            latestPost = LatestPost(key_name=keyName)
            latestPost.postDatetime = datetime.utcnow()
            latestPost.put()
            self.response.write('No post yet')
            return
        else:
            latestPostDate = latestPost.postDatetime

        # fetch public G+ stream
        urlGPlus = 'https://www.googleapis.com/plus/v1/people/{0}/activities/public?key={1}'.format(gplusUserID, apiKey)
        req = urllib2.Request(urlGPlus)
        response = urllib2.urlopen(req)
        jsonObj = json.load(response)
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.headers['charset'] = 'utf-8'
        repostQueue = []
        respost, postResult = None, None
        for acti in jsonObj['items']:
            if datetime.strptime(acti['published'], '%Y-%m-%dT%H:%M:%S.%fZ') > latestPostDate or datetime.strptime(acti['updated'], '%Y-%m-%dT%H:%M:%S.%fZ') > latestPostDate:
                respost = {}
                respost['content'] = ''
                respost['imgUrl'] = acti['actor']['image']['url'] # if there's no attachment, this should be my face
                respost['url'] = acti['url']
                respost['urlName'] = acti['title']
                respost['urlDescription'] = ''
                if acti['verb'] == 'post': # There's textual content(possibly an empty string, as long as it's not a resharing), so repost texual content
                    respost['content'] = strip_tags(acti['object']['content'])
                elif 'annotation' in acti: # this imply that acti['verb']=='share'
                    respost['content'] = strip_tags(acti['annotation'])
                # handle attachments of a post, like this "https://plus.google.com/111234960489880725462/posts/YgCiqa3i1hC"
                if 'attachments' in acti['object']:
                    if 'image' in acti['object']['attachments'][0]:
                        respost['imgUrl'] = acti['object']['attachments'][0]['image']['url'] # if there's attachment and it has pic, overwrite the original picture (which should be my face)
                    elif 'thumbnails' in acti['object']['attachments'][0]:
                        respost['imgUrl'] = acti['object']['attachments'][0]['thumbnails'][0]['image']['url']
                    if 'displayName' in acti['object']['attachments'][0]:
                        respost['urlDescription'] = acti['object']['attachments'][0]['displayName']
                repostQueue.append(respost)

        # obtain FB app access token
        if repostQueue > 0:
            urlFB_appAccessToken = 'https://graph.facebook.com/oauth/access_token?client_id={0}&client_secret={1}&grant_type=client_credentials'.format(FB_appID, FB_appSecret)
            req = urllib2.Request(urlFB_appAccessToken)
            resp = urllib2.urlopen(req).read()
            assert resp[:13] == 'access_token=', 'API changed'
            appAccessToken = resp[13:]
            urlFB_postToTimeline = 'https://graph.facebook.com/{0}/feed'.format(fbUserID)

            # transform G+ post into a FB post
            for rp in repostQueue:
                data = {'access_token':appAccessToken, 'link':unicode(rp['url']).encode('utf-8'), 'name':unicode(rp['urlName']).encode('utf-8'), 'description':unicode(rp['urlDescription']).encode('utf-8'), 'picture':unicode(rp['imgUrl']).encode('utf-8'), 'message':unicode(rp['content']).encode('utf-8')} # message, picture, link, name, description
                data = urllib.urlencode(data)
                req = urllib2.Request(urlFB_postToTimeline)

                # check whether repost successful
                postResult = urllib2.urlopen(req, data).read()
                if postResult is not None: # repost successfully
                    latestPost.postDatetime = datetime.utcnow()
                    latestPost.put()

            self.response.write('{0}\n{1}\n{2}'.format(respost, latestPostDate, postResult))
        else:
            return

application = webapp2.WSGIApplication([
    ('/', FetchAndRepost),
], debug=True)