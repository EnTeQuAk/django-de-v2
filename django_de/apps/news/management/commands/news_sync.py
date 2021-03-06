"""
This command allows the news in the db and on twitter to be synchrnoized.
"""
from optparse import make_option
import logging
import tweepy
import pytz

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from ... import models, utils


LOG = logging.getLogger(__name__)

class Command(BaseCommand):

    option_list = BaseCommand.option_list + (
            make_option('--dry-run', action='store_true',
                dest='dryrun', default=False),
            make_option('--page-size', action='store',
                dest='pagesize', default=100),
            )

    def handle(self, *args, **options):
        last_sync = models.NewsItem.objects.exported()\
                .order_by('-twitter_id')[:1]
        if last_sync:
            last_sync = last_sync[0].twitter_id
        else:
            last_sync = None

        api = utils.get_twitter_api()
        self.import_from_twitter(api, last_sync, options)
        self.export_to_twitter(api, options)

    def import_from_twitter(self, api, last_sync, options):
        pagesize = int(options['pagesize'])
        local_tz = pytz.timezone(settings.TIME_ZONE)
        LOG.info("Following tweets are imported")
        # In general the Twitter API provides data in a reverse chronological
        # fashion. So to receive a mostly valid sequence of items, the items
        # have to be reversed before being processed. The downside to this is
        # that also the resulting pages should be traversed in reverse order.
        # But for the primary scenario, a page limit of 100 should be more than
        # enough to not require paging at all. For all other cases, items
        # should always be presented sorted by pub_date.
        for page in tweepy.Cursor(api.user_timeline, since_id=last_sync,
                count=100).pages():
            for tweet in reversed(page):
                if tweet.in_reply_to_status_id is not None:
                    continue
                LOG.info(" + " + str(tweet.id))
                if options['dryrun']:
                    continue
                item = models.NewsItem(title=tweet.text,
                        pub_date=pytz.utc.localize(tweet.created_at)\
                                .astimezone(local_tz),
                        twitter_id=tweet.id)
                item.save()

    def export_to_twitter(self, api, options):
        LOG.info("Exporting following news items:")
        for item in models.NewsItem.objects.to_export().order_by('pub_date'):
            LOG.info(" + " + str(item.pk))
            LOG.info("   " + item.as_twitter_message())
            if options['dryrun']:
                continue
            result = api.update_status(item.as_twitter_message())
            if result is not None:
                item.twitter_id = result.id
                LOG.info("     -> " + str(result.id))
                item.save()
