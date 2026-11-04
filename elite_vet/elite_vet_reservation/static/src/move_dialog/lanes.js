/** @odoo-module **/
/**
 * Request 4. 11.: reservations of one room may overlap. Overlapping cards sit side by side, otherwise
 * the later one would cover the earlier one completely. Used by the backend board and the till's board.
 */

function eventKey(e) {
    return `${e.kind}-${e.id}`;
}

/** Map of eventKey -> {lane, lanes} for the events of one room (blocks stay across the column). */
function assignLanes(events) {
    const result = new Map();
    let cluster = [];
    let laneEnds = [];
    let clusterEnd = -1;
    const closeCluster = () => {
        for (const [e, lane] of cluster) {
            result.set(eventKey(e), { lane, lanes: laneEnds.length });
        }
        cluster = [];
        laneEnds = [];
    };
    const sorted = events.filter((e) => e.kind !== "block").sort((a, b) => a.start - b.start || a.end - b.end);
    for (const e of sorted) {
        if (e.start >= clusterEnd) {
            closeCluster();
        }
        let lane = laneEnds.findIndex((end) => end <= e.start);
        if (lane < 0) {
            lane = laneEnds.length;
        }
        laneEnds[lane] = e.end;
        clusterEnd = Math.max(clusterEnd, e.end);
        cluster.push([e, lane]);
    }
    closeCluster();
    return result;
}

/** CSS position of `e` among `events`; `left` = pixels taken by the doctor bands. */
export function laneStyle(events, e, left) {
    const { lane, lanes } = assignLanes(events).get(eventKey(e)) || { lane: 0, lanes: 1 };
    if (lanes < 2) {
        return `left:${left}px`;
    }
    const free = `(100% - ${left + 4}px)`;
    return `left:calc(${left}px + ${free} * ${lane} / ${lanes});right:auto;width:calc(${free} / ${lanes} - 2px)`;
}
