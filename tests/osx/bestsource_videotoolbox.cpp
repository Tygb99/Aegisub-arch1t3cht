#include "videosource.h"

extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/hwcontext.h>
#include <libavutil/imgutils.h>
#include <libavutil/pixdesc.h>
#include <libswscale/swscale.h>
}

#include <xxhash.h>
#include <algorithm>
#include <dlfcn.h>
#include <iostream>
#include <numeric>
#include <random>
#include <stdexcept>

namespace {
size_t hardware_frames = 0, transfers = 0, software_in_hw_context = 0, seeks = 0;

template<class Function>
Function original(const char *name) {
	auto function = reinterpret_cast<Function>(dlsym(RTLD_NEXT, name));
	if (!function) {
		std::cerr << "Cannot observe FFmpeg function: " << name << '\n';
		std::exit(2);
	}
	return function;
}

void require(bool condition, const std::string &message) {
	if (!condition) throw std::runtime_error(message);
}
}

// BestSource is linked statically: these observe its calls into FFmpeg without
// modifying R8. Returned BestVideoFrames have already been downloaded to RAM.
extern "C" int avcodec_receive_frame(AVCodecContext *context, AVFrame *frame) {
	static auto receive = original<decltype(&avcodec_receive_frame)>("avcodec_receive_frame");
	int result = receive(context, frame);
	if (result == 0 && context->hw_device_ctx) {
		if (frame->format == AV_PIX_FMT_VIDEOTOOLBOX) {
			if (hardware_frames++ == 0)
				std::cout << "Observed decoder=" << context->codec->name
					<< " received_pix_fmt=" << av_get_pix_fmt_name(AV_PIX_FMT_VIDEOTOOLBOX)
					<< " hw_frames_ctx=" << bool(frame->hw_frames_ctx) << std::endl;
		}
		else ++software_in_hw_context;
	}
	return result;
}

extern "C" int av_hwframe_transfer_data(AVFrame *destination, const AVFrame *source, int flags) {
	static auto transfer = original<decltype(&av_hwframe_transfer_data)>("av_hwframe_transfer_data");
	int result = transfer(destination, source, flags);
	if (result == 0 && source->format == AV_PIX_FMT_VIDEOTOOLBOX) ++transfers;
	return result;
}

extern "C" int av_seek_frame(AVFormatContext *context, int stream, int64_t timestamp, int flags) {
	static auto seek = original<decltype(&av_seek_frame)>("av_seek_frame");
	int result = seek(context, stream, timestamp, flags);
	if (result >= 0) ++seeks;
	return result;
}

namespace {
struct Fingerprint {
	int64_t pts;
	uint64_t hash;
	bool operator==(const Fingerprint &other) const { return pts == other.pts && hash == other.hash; }
};

Fingerprint fingerprint(BestVideoSource &source, int64_t n, bool linear) {
	std::unique_ptr<BestVideoFrame> frame(source.GetFrame(n, linear));
	require(bool(frame), "Missing frame " + std::to_string(n));
	const AVFrame *avframe = frame->GetAVFrame();
	require(avframe->pts == source.GetFrameInfo(n).PTS, "Frame/index PTS mismatch at " + std::to_string(n));
	// Canonical planar pixels let NV12 hardware output and YUV420P software
	// output compare byte-for-byte, excluding allocation padding.
	constexpr auto format = AV_PIX_FMT_YUV420P;
	std::vector<uint8_t> pixels(av_image_get_buffer_size(format, frame->Width, frame->Height, 1));
	uint8_t *planes[4] = {};
	int strides[4] = {};
	av_image_fill_arrays(planes, strides, pixels.data(), format, frame->Width, frame->Height, 1);
	SwsContext *converter = sws_getContext(frame->Width, frame->Height, static_cast<AVPixelFormat>(avframe->format),
		frame->Width, frame->Height, format, SWS_POINT, nullptr, nullptr, nullptr);
	require(converter != nullptr, "Cannot canonicalize decoded pixels");
	int rows = sws_scale(converter, avframe->data, avframe->linesize, 0, frame->Height, planes, strides);
	sws_freeContext(converter);
	require(rows == frame->Height, "Incomplete pixel conversion");
	return {avframe->pts, XXH3_64bits(pixels.data(), pixels.size())};
}

std::vector<Fingerprint> sequential(const char *movie, const std::string &device) {
	BestVideoSource source(movie, device, 0, -1, false, 0, bcmDisable, "", nullptr);
	source.SetMaxCacheSize(0);
	const auto &properties = source.GetVideoProperties();
	require(properties.NumFrames > 0, "No decoded frames");
	std::vector<Fingerprint> frames;
	for (int64_t n = 0; n < properties.NumFrames; ++n) frames.push_back(fingerprint(source, n, true));
	std::cout << "Sequential device=" << (device.empty() ? "CPU" : device)
		<< " frames=" << frames.size() << " time_base=" << properties.TimeBase.Num << '/' << properties.TimeBase.Den
		<< " first_pts=" << frames.front().pts << " last_pts=" << frames.back().pts
		<< " first_hash=" << std::hex << frames.front().hash << " last_hash=" << frames.back().hash << std::dec << '\n';
	return frames;
}
}

int main(int argc, char **argv) try {
	if (argc == 2 && std::string(argv[1]) == "--help") {
		std::cout << "Usage: bestsource_videotoolbox MOVIE [--software]\n"
			"Verify real hardware frames, sequential CPU equality, uncached random seeks and cancellation.\n";
		return 0;
	}
	require(argc == 2 || (argc == 3 && std::string(argv[2]) == "--software"),
		"Usage: bestsource_videotoolbox MOVIE [--software]");
	av_log_set_level(AV_LOG_VERBOSE);
	std::string device = argc == 3 ? "" : "videotoolbox";
	auto reference = sequential(argv[1], device);
	if (!device.empty()) {
		require(hardware_frames > 0 && transfers > 0 && software_in_hw_context == 0,
			"Hardware request did not produce VideoToolbox frames with successful downloads");
		require(reference == sequential(argv[1], ""), "Hardware and CPU sequential PTS/pixels differ");
	}
	BestVideoSource random(argv[1], device, 0, -1, false, 0, bcmDisable, "", nullptr);
	random.SetMaxCacheSize(0);
	random.SetSeekPreRoll(12);
	require(random.GetVideoProperties().NumFrames == static_cast<int64_t>(reference.size()), "Frame count changed");
	std::vector<int64_t> order(reference.size());
	std::iota(order.begin(), order.end(), 0);
	std::mt19937 generator(0x4253);
	std::shuffle(order.begin(), order.end(), generator);
	for (auto n : order)
		require(fingerprint(random, n, false) == reference[n], "Random seek PTS/pixel mismatch at " + std::to_string(n));
	require(!random.GetFrame(-1) && !random.GetFrame(reference.size()), "Out-of-range frame returned");
	std::cout << "Random seeks checked=" << order.size() << " demux_seeks=" << seeks
		<< " forced_linear=" << random.GetLinearDecodingState() << '\n';
	bool cancelled = false;
	try {
		BestVideoSource cancel(argv[1], device, 0, -1, false, 0, bcmDisable, "", nullptr,
			[](int, int64_t, int64_t) { return false; });
	} catch (const BestSourceException &error) {
		cancelled = std::string(error.what()) == "Indexing canceled by user";
	}
	require(cancelled, "Indexing cancellation was not propagated");
	std::cout << "PASS hardware_frames=" << hardware_frames << " downloads=" << transfers
		<< " software_in_hw_context=" << software_in_hw_context << " cancellation=propagated\n";
	return 0;
} catch (const std::exception &error) {
	std::cerr << "FAIL: " << error.what() << '\n';
	return 1;
}
