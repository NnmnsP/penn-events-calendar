import shortid from 'shortid';
import moment from 'moment';
import XMLParser from 'xml-js';

class XML {
  // define xml2json function
  static xml2json(xml) {
    return JSON.parse(XMLParser
      .xml2json(
        xml,
        { compact: true, spaces: 2 },
      ));
  }
}

class Key {
  static getShortKey() {
    return shortid.generate();
  }
}

class Datetime {
  static getMonthDay(dtStr) {
    return moment(dtStr).format('MM.DD').toString();
  }

  static getTime(timeStr) {
    // console.log(moment(timeStr, 'HH:mm:ss').format('LT'));
    return moment(timeStr, 'HH:mm:ss').format('HH:MM A');
  }

  static getDayMonthDate(timeStr) {
    return moment(timeStr).format('ddd, MMM DD');
  }
}

class Events {
  static getText(eventItem) {
    return {
      date: eventItem.date._text,
      starttime: eventItem.starttime._text,
      endtime: eventItem.endtime._text,
      title: eventItem.title._text,
      description: eventItem.description._text,
      location: eventItem.location._text,
      room: eventItem.room._text,
      url: eventItem.url._text,
      student: eventItem.student._text,
      privacy: eventItem.privacy._text,
      category: eventItem.category._text,
      school: eventItem.school._text,
      owner: eventItem.owner._text,
      link: eventItem.link._text,
    };
  }

  static getId(eventItem) {
    return eventItem.link._attributes.id;
  }

  static groupByDate(eventArr) {
    // get all dates from events
    const allDates = eventArr.map(ev => ev.date);
    // get only unique dates
    const uniqueDates = [...new Set(allDates)];
    // groupby date with reduce
    const groupbyDate = uniqueDates.reduce((acc, cur) =>
      ([
        ...acc,
        {
          dateFormatted: Datetime.getDayMonthDate(cur),
          events: eventArr.filter(ev =>
            ev.date === cur),
        },
      ]), []);

    return groupbyDate;
  }
}

export { Datetime, Events, Key, XML };
