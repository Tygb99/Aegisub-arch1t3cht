#include "include/aegisub/video_provider.h"
#include "bestsource_common.h"
#include "options.h"
#include "video_frame.h"

#include <libaegisub/background_runner.h>
#include <libaegisub/dispatch.h>
#include <libaegisub/fs.h>
#include <libaegisub/log.h>

extern "C" {
#include <libavcodec/avcodec.h>
#include <libavutil/hwcontext.h>
#include <libavutil/md5.h>
}

#include <dlfcn.h>
#include <fstream>
#include <iostream>
#include <numeric>
#include <random>
#include <stdexcept>

std::unique_ptr<VideoProvider> CreateBSVideoProvider(agi::fs::path const&, std::string const&, agi::BackgroundRunner *);
namespace config { agi::Options *opt = nullptr; }
namespace {
std::string cache_path;
size_t hardware_frames = 0, cpu_frames = 0;
void require(bool condition, const std::string &message) {
	if (!condition) throw std::runtime_error(message);
}

class Runner : public agi::BackgroundRunner, public agi::ProgressSink {
public:
	bool cancel_index = false;
	bool cancelled = false;
	void Run(std::function<void(agi::ProgressSink *)> task) override { task(this); }
	void SetIndeterminate() override { }
	void SetTitle(std::string const&) override { }
	void SetMessage(std::string const&) override { }
	void SetProgress(int64_t, int64_t) override { cancelled = cancel_index; }
	void Log(std::string const&) override { }
	void SetStayOpen(bool) override { }
	bool IsCancelled() override { return cancelled; }
};
}

namespace provider_bs {
std::pair<TrackSelection, bool> SelectTrack(agi::fs::path const&, bool) { return {static_cast<TrackSelection>(0), false}; }
std::string GetCacheFile(agi::fs::path const&) { return cache_path; }
void CleanBSCache() { }
}

std::unique_ptr<VideoProvider> CreateDummyVideoProvider(agi::fs::path const&, std::string const&, agi::BackgroundRunner *) {
	throw std::runtime_error("Unexpected Dummy provider factory");
}
std::unique_ptr<VideoProvider> CreateYUV4MPEGVideoProvider(agi::fs::path const&, std::string const&, agi::BackgroundRunner *) {
	throw std::runtime_error("Unexpected YUV4MPEG provider factory");
}
std::unique_ptr<VideoProvider> CreateFFmpegSourceVideoProvider(agi::fs::path const&, std::string const&, agi::BackgroundRunner *) {
	throw std::runtime_error("Unexpected FFmpegSource provider factory");
}

extern "C" int avcodec_receive_frame(AVCodecContext *context, AVFrame *frame) {
	static auto receive = reinterpret_cast<decltype(&avcodec_receive_frame)>(dlsym(RTLD_NEXT, "avcodec_receive_frame"));
	require(receive != nullptr, "Cannot observe FFmpeg receive_frame");
	int result = receive(context, frame);
	if (result == 0) {
		if (frame->format == AV_PIX_FMT_VIDEOTOOLBOX) ++hardware_frames;
		else ++cpu_frames;
	}
	return result;
}

int main(int argc, char **argv) try {
	if (argc == 2 && std::string(argv[1]) == "--help") {
		std::cout << "Usage: bestsource_provider MOVIE MACOS_CONFIG SCRATCH_DIRECTORY\n";
		return 0;
	}
	require(argc == 4, "Usage: bestsource_provider MOVIE MACOS_CONFIG SCRATCH_DIRECTORY");
	agi::dispatch::Init([](agi::dispatch::Thunk) { throw std::runtime_error("Unexpected UI dispatch"); });
	agi::log::LogSink log;
	agi::log::log = &log;
	av_log_set_level(AV_LOG_ERROR);
	std::ifstream config_file(argv[2]);
	std::string defaults((std::istreambuf_iterator<char>(config_file)), {});
	agi::Options options("", {defaults.data(), defaults.size()}, agi::Options::FLUSH_SKIP);
	config::opt = &options;
	require(OPT_GET("Video/Provider")->GetString() == "BestSource", "macOS video default is not BestSource");
	require(OPT_GET("Audio/Provider")->GetString() == "FFmpegSource", "macOS audio default changed");
	require(OPT_GET("Provider/Video/BestSource/Hardware Decoding")->GetBool(), "macOS hardware default is disabled");
	OPT_SET("Provider/Video/BestSource/Max Cache Size")->SetInt(0);
	Runner runner;
	cache_path = std::string(argv[3]) + "/hardware";
	auto hardware = CreateBSVideoProvider(argv[1], "TV.709", &runner);
	require(hardware_frames > 0, "Provider did not decode hardware frames");
	std::vector<std::array<uint8_t, 16>> frames;
	VideoFrame frame;
	std::array<uint8_t, 16> hash;
	for (int n = 0; n < hardware->GetFrameCount(); ++n) {
		hardware->GetFrame(n, frame);
		av_md5_sum(hash.data(), frame.data.data(), frame.data.size());
		frames.push_back(hash);
	}
	std::vector<int> order(frames.size());
	std::iota(order.begin(), order.end(), 0);
	std::mt19937 generator(0x4253);
	std::shuffle(order.begin(), order.end(), generator);
	for (int n : order) {
		hardware->GetFrame(n, frame);
		av_md5_sum(hash.data(), frame.data.data(), frame.data.size());
		require(hash == frames[n], "Provider random-seek pixels differ at " + std::to_string(n));
	}
	std::cout << "PASS provider hardware_frames=" << hardware_frames << " random_frames=" << order.size() << '\n';
	OPT_SET("Provider/Video/BestSource/Hardware Decoding")->SetBool(false);
	size_t before = hardware_frames;
	cache_path = std::string(argv[3]) + "/software";
	auto software = CreateBSVideoProvider(argv[1], "TV.709", &runner);
	require(hardware_frames == before, "Disabled preference still used hardware");
	require(hardware->GetFrameCount() == software->GetFrameCount(), "Provider frame counts differ");
	require(hardware->GetKeyFrames() == software->GetKeyFrames(), "Provider keyframes differ");
	for (int n : order) {
		require(hardware->GetFPS().TimeAtFrame(n) == software->GetFPS().TimeAtFrame(n), "Provider timecodes differ");
	}
	std::cout << "PASS preference=false uses CPU; frame counts, keyframes and timecodes match\n";
	OPT_SET("Provider/Video/BestSource/Hardware Decoding")->SetBool(true);
	auto raw_path = std::string(argv[3]) + "/unsupported.y4m";
	std::ofstream raw(raw_path, std::ios::binary);
	raw << "YUV4MPEG2 W16 H16 F25:1 Ip A1:1 C420jpeg\n";
	for (int n = 0; n < 8; ++n) raw << "FRAME\n" << std::string(384, static_cast<char>(n + 32));
	raw.close();
	cache_path = std::string(argv[3]) + "/unsupported-cache";
	before = cpu_frames;
	auto fallback = CreateBSVideoProvider(raw_path, "TV.601", &runner);
	fallback->GetFrame(7, frame);
	require(fallback->GetFrameCount() == 8 && frame.data.size() == 16 * 16 * 4 && cpu_frames > before,
		"Unsupported codec did not fall back to usable CPU frames");
	bool unsupported_logged = false;
	for (const auto &message : log.GetMessages()) {
		if (message.severity == agi::log::Warning) {
			std::cout << "Fallback log: " << message.message << '\n';
			unsupported_logged = true;
		}
	}
	require(unsupported_logged, "Actual unsupported decoder was not logged");
	runner.cancel_index = true;
	cache_path = std::string(argv[3]) + "/cancel-cache";
	bool cancelled = false;
	auto messages_before = log.GetMessages().size();
	try { auto cancel = CreateBSVideoProvider(argv[1], "TV.709", &runner); }
	catch (const agi::UserCancelException &) { cancelled = true; }
	require(cancelled, "Provider swallowed indexing cancellation");
	auto messages = log.GetMessages();
	for (size_t i = messages_before; i < messages.size(); ++i)
		require(messages[i].severity != agi::log::Warning, "Cancellation triggered CPU fallback");
	std::cout << "PASS unsupported codec falls back; cancellation propagates without fallback\n";
	runner.cancel_index = false;
	runner.cancelled = false;
	bool failed = false;
	try { auto missing = CreateBSVideoProvider(raw_path + ".missing", "TV.601", &runner); }
	catch (const VideoOpenError &error) {
		failed = error.GetMessage().find(raw_path + ".missing") != std::string::npos;
	}
	require(failed, "CPU fallback failure lost the original source error");
	std::cout << "PASS both decode attempts failing preserves the detailed error\n";
	return 0;
} catch (const agi::Exception &error) {
	std::cerr << "FAIL: " << error.GetMessage() << '\n';
	return 1;
} catch (const std::exception &error) {
	std::cerr << "FAIL: " << error.what() << '\n';
	return 1;
}
