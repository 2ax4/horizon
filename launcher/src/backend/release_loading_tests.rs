use super::*;
use std::cell::RefCell;
use std::hint::black_box;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::{Duration, Instant};

fn fixture() -> String {
    let mut list: Vec<_> = (1..=99)
        .map(|i| {
            serde_json::json!({
                "tag_name": format!("v2026.10.14.{i}"),
                "name": format!("Build {i}"), "body": "Release notes\r\n".repeat(256),
                "published_at": "2026-10-14T12:00:00Z", "draft": i == 99,
                "assets": [{"name": ASSET.unwrap_or("unsupported"),
                    "browser_download_url": "https://example.test/game", "size": 12345}]
            })
        })
        .collect();
    list.push(serde_json::json!({
        "tag_name": "launcher@99.0.0", "name": "Launcher", "body": "Notes",
        "assets": [{"name": LAUNCHER_ASSET.unwrap_or("unsupported"),
            "browser_download_url": "https://example.test/launcher", "size": 6789}]
    }));
    serde_json::to_string(&list).unwrap()
}

fn installed_fixture() -> Vec<String> {
    vec!["v2026.10.14.50".into()]
}

// The former startup paths: each decodes its own response; the update path parses games again.
fn baseline(load: impl Fn() -> Result<serde_json::Value, String>) -> (Vec<Release>, Updates) {
    let releases = parse_releases(&load().unwrap(), ASSET, is_game_tag);
    let list = load().unwrap();
    let updates = Updates {
        horizon: horizon_update(
            &parse_releases(&list, ASSET, is_game_tag),
            &installed_fixture(),
        ),
        launcher: launcher_update(&parse_releases(&list, LAUNCHER_ASSET, is_launcher_tag)),
    };
    (releases, updates)
}

fn shared(
    load: impl FnOnce() -> Result<serde_json::Value, String> + Copy,
    fork_load: impl FnOnce() -> Result<serde_json::Value, String>,
) -> (Vec<Release>, Updates) {
    let mut releases = None;
    let updates = releases_and_updates_with(
        load,
        installed_fixture,
        |list| parse_releases(list, LAUNCHER_ASSET, is_launcher_tag),
        fork_load,
        |r| releases = Some(r.unwrap()),
    )
    .unwrap();
    (releases.unwrap(), updates)
}

fn fork_fixture() -> String {
    serde_json::to_string(&[serde_json::json!({
        "tag_name": "launcher@98.0.0-offline", "name": "Launcher", "body": "Notes",
        "assets": [{"name": LAUNCHER_ASSET.unwrap_or("unsupported"),
            "browser_download_url": "https://example.test/fork-launcher", "size": 6789}]
    })])
    .unwrap()
}

#[test]
fn the_launcher_updates_from_the_fork_only() {
    let text = fixture();
    let mut published = None;
    let updates = releases_and_updates_with(
        || Ok(serde_json::from_str(&text).unwrap()),
        installed_fixture,
        |list| parse_releases(list, LAUNCHER_ASSET, is_launcher_tag),
        || Ok(serde_json::from_str(&fork_fixture()).unwrap()),
        |r| published = Some(r.unwrap()),
    )
    .unwrap();
    assert_eq!(published.unwrap()[0].tag, "v2026.10.14.98");
    assert_eq!(
        updates.launcher.map(|r| r.tag),
        Some("launcher@98.0.0-offline".into())
    );
}

#[test]
fn a_fork_tag_newer_than_this_launcher_is_the_update() {
    let asset = || Some((String::from("https://example.test/fork-launcher"), 1));
    let release = |tag: &str| Release {
        tag: tag.into(),
        name: tag.into(),
        body: String::new(),
        date: String::new(),
        time: String::new(),
        asset: asset(),
        prerelease: false,
        nightly: None,
    };
    let own = "launcher@0.2.29-offline";
    assert!(launcher_update_from(&[release("launcher@0.2.29-offline")], own).is_none());
    assert_eq!(
        launcher_update_from(&[release("launcher@0.2.30-offline")], own)
            .unwrap()
            .tag,
        "launcher@0.2.30-offline"
    );
    assert_eq!(
        launcher_version("launcher@0.2.30-offline"),
        Some("0.2.30-offline")
    );
}

#[test]
fn errors_reach_releases_and_updates_without_fallback() {
    for error in [
        "No connection: offline",
        "GitHub's rate limit was reached.",
        "invalid JSON",
    ] {
        let mut published = None;
        let result = releases_and_updates_with(
            || Err(error.into()),
            || panic!("no installed scan after failure"),
            |_| panic!("no fallback after failure"),
            || panic!("no fork lookup after failure"),
            |r| published = Some(r),
        );
        assert_eq!(published.unwrap().unwrap_err(), error);
        assert_eq!(result.unwrap_err(), error);
    }
}

#[test]
fn publish_games_before_the_fork_launcher_lookup() {
    let events = RefCell::new(Vec::new());
    let result = releases_and_updates_with(
        || Ok(serde_json::json!([{"tag_name": "v2026.10.14", "assets": []}])),
        Vec::new,
        |list| {
            launcher_releases_in_with(list, |url| {
                assert_eq!(events.borrow().first(), Some(&"releases"));
                events.borrow_mut().push("fallback");
                if url.contains("matching-refs") {
                    Ok(serde_json::json!([{"ref": "refs/tags/launcher@99.0.0-offline"}]))
                } else {
                    Ok(
                        serde_json::json!({"tag_name": "launcher@99.0.0-offline", "assets": [{
                            "name": LAUNCHER_ASSET.unwrap_or("unsupported"),
                            "browser_download_url": "u", "size": 1
                        }]}),
                    )
                }
            })
        },
        || Ok(serde_json::json!([])),
        |r| {
            assert_eq!(r.unwrap()[0].tag, "v2026.10.14");
            events.borrow_mut().push("releases");
        },
    )
    .unwrap();
    assert_eq!(*events.borrow(), ["releases", "fallback", "fallback"]);
    assert_eq!(result.launcher.is_some(), LAUNCHER_ASSET.is_some());
}

#[test]
fn failed_fork_lookup_keeps_game_result_and_no_launcher_update() {
    let requests = AtomicUsize::new(0);
    for day in [14, 15] {
        let mut published = None;
        let updates = releases_and_updates_with(
            || {
                requests.fetch_add(1, Ordering::Relaxed);
                Ok(serde_json::json!([{"tag_name": format!("v2026.10.{day}")}
                ]))
            },
            Vec::new,
            |list| launcher_releases_in_with(list, |_| Err("offline".into())),
            || Err("offline".into()),
            |r| published = Some(r.unwrap()),
        )
        .unwrap();
        assert_eq!(published.unwrap()[0].tag, format!("v2026.10.{day}"));
        assert!(updates.launcher.is_none());
    }
    assert_eq!(requests.load(Ordering::Relaxed), 2);
}

#[test]
#[ignore = "local release-loading benchmark; run explicitly with --ignored --nocapture"]
fn benchmark_shared_startup_response() {
    let text = fixture();
    let requests = AtomicUsize::new(0);
    let load = |delay: Duration| {
        requests.fetch_add(1, Ordering::Relaxed);
        if !delay.is_zero() {
            std::thread::sleep(delay);
        }
        serde_json::from_str(black_box(&text)).map_err(|e| e.to_string())
    };
    let old = || baseline(|| load(Duration::ZERO));
    let new = || shared(|| load(Duration::ZERO), || load(Duration::ZERO));
    assert_eq!(
        serde_json::to_value(old()).unwrap(),
        serde_json::to_value(new()).unwrap()
    );
    let concurrent_old = || {
        std::thread::scope(|scope| {
            let releases = scope.spawn(|| {
                parse_releases(&load(Duration::from_millis(5)).unwrap(), ASSET, is_game_tag)
            });
            let updates = scope.spawn(|| {
                let list = load(Duration::from_millis(5)).unwrap();
                Updates {
                    horizon: horizon_update(
                        &parse_releases(&list, ASSET, is_game_tag),
                        &installed_fixture(),
                    ),
                    launcher: launcher_update(&parse_releases(
                        &list,
                        LAUNCHER_ASSET,
                        is_launcher_tag,
                    )),
                }
            });
            (releases.join().unwrap(), updates.join().unwrap())
        })
    };
    let threaded_new = || {
        std::thread::scope(|scope| {
            scope
                .spawn(|| {
                    shared(
                        || load(Duration::from_millis(5)),
                        || load(Duration::from_millis(5)),
                    )
                })
                .join()
                .unwrap()
        })
    };
    assert_eq!(
        serde_json::to_value(concurrent_old()).unwrap(),
        serde_json::to_value(threaded_new()).unwrap()
    );
    fn measure<T>(run: impl Fn() -> T, requests: &AtomicUsize) -> (u128, usize) {
        for _ in 0..20 {
            black_box(run());
        }
        requests.store(0, Ordering::Relaxed);
        let mut times: Vec<_> = (0..201)
            .map(|_| {
                let start = Instant::now();
                black_box(run());
                start.elapsed().as_nanos()
            })
            .collect();
        times.sort_unstable();
        (times[100], requests.load(Ordering::Relaxed))
    }
    println!(
        "fixture={} bytes; 100 releases; 20 warmups, 201 samples; median ns",
        text.len()
    );
    for (label, before, after) in [
        (
            "serial zero-delay work",
            measure(old, &requests),
            measure(new, &requests),
        ),
        (
            "concurrent startup, 5ms/request",
            measure(concurrent_old, &requests),
            measure(threaded_new, &requests),
        ),
    ] {
        assert_eq!((before.1, after.1), (402, 402));
        println!(
            "{label}: before={} after={} ratio={:.3}x requests={}->{}",
            before.0,
            after.0,
            before.0 as f64 / after.0 as f64,
            before.1,
            after.1
        );
    }
}
